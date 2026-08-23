# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for driving DNS-01 issuance of the main domain from the stored config.

The last link: the panel writes the credentials, and this is what puts them on
the wire. Everything below it has been able to issue this way for several
changes and had nothing feeding it.

The judgement here is when NOT to call. A DNS-01 issuance against a delegation
that does not exist is not a maybe: the certificate authority asks a public
resolver for the challenge record, gets nothing, and fails. Each of those
failures counts against a validation rate limit that is per account and per
hostname and refills slowly, and this runs on every apiv4 start and on every
save. A deployment whose CNAME has not been created yet would burn that limit
on certain failures and then be unable to issue for an hour after the operator
finally fixes the DNS -- which is exactly when they are watching.

So issuance waits for the delegation to have been seen. That is a decision with
a cost: an operator who pastes credentials by hand and never presses the check
button gets no certificate. It is paid for by the panel, which says on its one
status line whether the delegation is verified, and by the log line here that
says the same thing in the same words.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def bastion():
    from isardvdi_common.helpers.bastion import Bastion

    return Bastion


@pytest.fixture
def stored_config(bastion):
    state = {"config": {}}

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch.object(bastion, "_rdb_context", classmethod(lambda cls: _Ctx())), patch(
        "isardvdi_common.helpers.bastion.r"
    ) as mock_r, patch.object(
        type(bastion), "_rdb_connection", property(lambda self: MagicMock())
    ), patch(
        "isardvdi_common.helpers.bastion._haproxy_bastion_client"
    ), patch.object(
        bastion, "_call_grpc_with_infinite_retry"
    ) as mock_call:
        mock_r.table.return_value.get.return_value.default.return_value.run.side_effect = lambda *a, **k: state[
            "config"
        ]
        yield state, mock_call


def _configured(**overrides):
    acmedns = {
        "base_url": "https://auth.example.com",
        "username": "eabcdb41-d89f-4580-826f-3e62e9755ef2",
        "password": "not-a-real-password-for-tests-0123456789",
        "subdomain": "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
        "fulldomain": "d420c923.auth.example.com",
        "verified": True,
    }
    acmedns.update(overrides)
    return {
        "certificates": {
            "main_domain": {
                "certificate_source": "acme_dns",
                "names": ["vdi.example.com"],
                "acme_server": "letsencrypt",
                "email": "ops@example.com",
                "acmedns": acmedns,
            }
        }
    }


def _request(mock_call):
    return mock_call.call_args.args[1]


# ── Issuing ──────────────────────────────────────────────────────────────


class TestIssuing:
    def test_it_sends_the_credentials(self, bastion, stored_config):
        state, mock_call = stored_config
        state["config"] = _configured()

        bastion.issue_main_domain_certificate()

        request = _request(mock_call)
        assert request.acme_dns_base_url == "https://auth.example.com"
        assert request.acme_dns_username == "eabcdb41-d89f-4580-826f-3e62e9755ef2"
        assert request.acme_dns_password == "not-a-real-password-for-tests-0123456789"
        assert request.acme_dns_subdomain == "d420c923-bbd7-4056-ab64-c3ca54c9b3cf"

    def test_the_names_and_the_account_still_travel(self, bastion, stored_config):
        """acme_server and email describe the certificate authority account,
        which DNS-01 needs exactly as much as HTTP-01 does."""
        state, mock_call = stored_config
        state["config"] = _configured()

        bastion.issue_main_domain_certificate()

        request = _request(mock_call)
        assert list(request.names) == ["vdi.example.com"]
        assert request.acme_server == "letsencrypt"
        assert request.acme_email == "ops@example.com"

    def test_the_fulldomain_is_not_sent(self, bastion, stored_config):
        """It is what the operator delegates to, not something the issuance
        needs: acme.sh finds the record through the subdomain it writes."""
        state, mock_call = stored_config
        state["config"] = _configured()

        bastion.issue_main_domain_certificate()
        assert "d420c923.auth.example.com" not in str(_request(mock_call))


# ── Not issuing ──────────────────────────────────────────────────────────


class TestNotIssuing:
    def test_an_unverified_delegation_does_not_issue(self, bastion, stored_config):
        """The certificate authority will ask a public resolver for a record
        that is not there. Each failure counts against a validation rate limit
        that refills slowly, and this runs on every start and every save."""
        state, mock_call = stored_config
        state["config"] = _configured(verified=False)

        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_a_delegation_never_checked_does_not_issue(self, bastion, stored_config):
        """Absent is not the same as verified. A block written by a manual save
        has no flag at all, and treating that as ready would issue against a
        delegation nobody has ever looked at."""
        state, mock_call = stored_config
        config = _configured()
        del config["certificates"]["main_domain"]["acmedns"]["verified"]
        state["config"] = config

        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    @pytest.mark.parametrize(
        "missing", ["base_url", "username", "password", "subdomain"]
    )
    def test_incomplete_credentials_do_not_issue(self, bastion, stored_config, missing):
        """Three of four cannot answer a challenge. Sending them would spend a
        certificate authority order to find that out."""
        state, mock_call = stored_config
        config = _configured()
        del config["certificates"]["main_domain"]["acmedns"][missing]
        state["config"] = config

        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_no_credentials_at_all_do_not_issue(self, bastion, stored_config):
        """The state right after someone picks acme-dns in the panel and saves
        before registering anything."""
        state, mock_call = stored_config
        state["config"] = {
            "certificates": {
                "main_domain": {
                    "certificate_source": "acme_dns",
                    "names": ["vdi.example.com"],
                }
            }
        }

        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_a_domain_with_no_name_does_not_issue(self, bastion, stored_config):
        state, mock_call = stored_config
        config = _configured()
        config["certificates"]["main_domain"]["names"] = []
        state["config"] = config

        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()


# ── The other source is untouched ────────────────────────────────────────


def test_http01_still_sends_no_acme_dns_fields(bastion, stored_config):
    """A deployment on HTTP-01 must reach haproxy-sync with those fields empty,
    or the layer below reads it as a broken acme-dns configuration and refuses
    to issue anything at all."""
    state, mock_call = stored_config
    state["config"] = {
        "certificates": {
            "main_domain": {
                "certificate_source": "acme",
                "names": ["vdi.example.com"],
                "acme_server": "letsencrypt",
            }
        }
    }

    bastion.issue_main_domain_certificate()

    request = _request(mock_call)
    assert request.acme_dns_base_url == ""
    assert request.acme_dns_username == ""
    assert request.acme_dns_password == ""
    assert request.acme_dns_subdomain == ""
