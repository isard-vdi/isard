# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for driving main-domain certificate issuance from the stored config.

Two separable concerns, and the second is the one that can take an install down.

WHAT to issue: the read of ``config[1].certificates.main_domain``. An install
that never opened the new panel has no such block, and one that has a domain but
no ACME account has nothing to issue with. Both must be immediate no-ops, or the
gRPC call fires on every apiv4 start on every deployment in the fleet.

WHEN to issue: not on anything a caller is waiting for. The gRPC helper this goes
through retries up to 60 times with delays capped at 30s, and a certificate
authority round trip routinely outlives the 30s per-call timeout. On the lifespan
path that stalls apiv4's startup; inside the admin PUT it stalls the browser. So
issuance is dispatched to the background and the caller is released immediately.
"""

from unittest.mock import MagicMock, patch

import pytest

# ── What to issue ────────────────────────────────────────────────────────


@pytest.fixture
def bastion():
    from isardvdi_common.helpers.bastion import Bastion

    return Bastion


@pytest.fixture
def stored_config(bastion):
    """Patch the config read and the gRPC client the issuance goes through."""
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
    ) as mock_client, patch.object(
        bastion, "_call_grpc_with_infinite_retry"
    ) as mock_call:
        mock_r.table.return_value.get.return_value.default.return_value.run.side_effect = lambda *a, **k: state[
            "config"
        ]
        yield state, mock_call, mock_client


class TestNothingToIssue:
    def test_no_certificates_block_at_all(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = {"id": 1}
        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_no_main_domain_block(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = {"certificates": {}}
        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_no_certificate_source(self, bastion, stored_config):
        """The seeded, inert state: a domain is known but no ACME account is."""
        state, mock_call, _ = stored_config
        state["config"] = {
            "certificates": {"main_domain": {"names": ["vdi.example.com"]}}
        }
        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_no_names(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = {
            "certificates": {"main_domain": {"certificate_source": "acme", "names": []}}
        }
        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()

    def test_an_unknown_source_is_not_guessed_at(self, bastion, stored_config):
        """A value this release does not implement must not fall through to
        HTTP-01: issuing the wrong kind of certificate silently is worse than
        issuing none."""
        state, mock_call, _ = stored_config
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

    def test_a_missing_config_row(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = None
        assert bastion.issue_main_domain_certificate() is None
        mock_call.assert_not_called()


class TestIssuing:
    def test_sends_the_names_and_the_account(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = {
            "certificates": {
                "main_domain": {
                    "certificate_source": "acme",
                    "names": ["vdi.example.com", "alt.example.com"],
                    "email": "ops@example.com",
                    "acme_server": "letsencrypt",
                }
            }
        }
        bastion.issue_main_domain_certificate()
        request = mock_call.call_args.args[1]
        assert list(request.names) == ["vdi.example.com", "alt.example.com"]
        assert request.acme_email == "ops@example.com"
        assert request.acme_server == "letsencrypt"

    def test_a_missing_acme_server_is_not_invented(self, bastion, stored_config):
        state, mock_call, _ = stored_config
        state["config"] = {
            "certificates": {
                "main_domain": {
                    "certificate_source": "acme",
                    "names": ["vdi.example.com"],
                    "email": "ops@example.com",
                }
            }
        }
        bastion.issue_main_domain_certificate()
        assert mock_call.call_args.args[1].acme_server == ""


# ── When to issue ────────────────────────────────────────────────────────


class TestIssuanceIsOffTheRequestPath:
    def test_the_admin_save_does_not_wait_for_issuance(self):
        """The PUT persists and returns; the certificate authority round trip
        happens after the caller has been released."""
        from api.services.admin import certificates as service

        with patch.object(service, "CertificatesConfig") as mock_config, patch.object(
            service, "_dispatch_main_domain_issuance"
        ) as mock_dispatch:
            mock_config.get_certificates_config.return_value = {}
            service.AdminCertificatesService.update_certificates(
                {"main_domain": {"names": ["vdi.example.com"]}}
            )

        mock_dispatch.assert_called_once()

    def test_dispatch_does_not_run_issuance_inline(self):
        from api.services.admin import certificates as service

        with patch.object(service, "Bastion") as mock_bastion, patch.object(
            service.threading, "Thread"
        ) as mock_thread:
            service._dispatch_main_domain_issuance()

        mock_thread.assert_called_once()
        assert mock_thread.call_args.kwargs["daemon"] is True
        mock_bastion.issue_main_domain_certificate.assert_not_called()
        mock_thread.return_value.start.assert_called_once()

    def test_a_failed_issuance_does_not_reach_the_caller(self):
        """The configuration is already saved by then. Turning a certificate
        authority failure into a failed save would tell the admin their edit did
        not land, when it did."""
        from api.services.admin import certificates as service

        with patch.object(service, "Bastion") as mock_bastion:
            mock_bastion.issue_main_domain_certificate.side_effect = RuntimeError(
                "CA down"
            )
            # The worker body is what the thread would run.
            service._issue_main_domain_now()

    def test_startup_dispatches_instead_of_blocking(self):
        """The lifespan sync path must not wait either: with haproxy-sync slow
        or down, the retry budget alone is tens of minutes of stalled startup."""
        import api

        with patch("api.Bastion") as mock_bastion, patch(
            "api._dispatch_main_domain_issuance"
        ) as mock_dispatch:
            api._sync_haproxy_maps()

        mock_bastion.update_bastion_haproxy_map.assert_called_once()
        mock_bastion.sync_category_branding_domains.assert_called_once()
        mock_dispatch.assert_called_once()
        mock_bastion.issue_main_domain_certificate.assert_not_called()
