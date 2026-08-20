# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the main-domain certificate configuration in ``config[1].certificates``.

Three properties are pinned here, and each one corresponds to a way this
endpoint could quietly destroy an operator's configuration.

1. A PUT that carries only some of the fields must not wipe the rest. The
   service persists with ``replace_certificates_config``, which uses
   ``r.literal`` and therefore drops every key it is not handed. The route
   builds its payload with ``model_dump(exclude_none=True)``, so any field the
   admin form does not render simply is not in the dict. Without a merge over
   the stored document, saving the domain name alone silently discards the ACME
   account e-mail and server.

2. ``acme_challenge`` is derived from the certificate source for display and
   must never reach the database. It is a function of another stored field, so
   persisting it creates a second source of truth that can disagree.

3. ``names`` is a list from the first day. The shape is what is expensive to
   change later: a stored string would need a migration over live data plus a
   compatibility window in every reader. The list is ordered and ``names[0]``
   is the primary, which is load-bearing — acme.sh indexes the certificate by
   it.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

# ── Schema ───────────────────────────────────────────────────────────────


class TestMainDomainCertificateSchema:
    def test_accepts_a_list_of_names(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(
            names=["vdi.example.com"], certificate_source="acme"
        )
        assert cert.names == ["vdi.example.com"]

    def test_custom_is_not_a_source_this_release_offers(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        # "custom" is deliberately absent: widening a Literal later is
        # additive, narrowing one is a breaking change. "acme_dns" was absent
        # for the same reason until the release that could act on it, which is
        # this one -- see test_acme_dns_is_accepted below.
        with pytest.raises(ValidationError):
            MainDomainCertificate(
                names=["vdi.example.com"], certificate_source="custom"
            )

    def test_acme_dns_is_accepted(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(
            names=["vdi.example.com"], certificate_source="acme_dns"
        )
        assert cert.certificate_source == "acme_dns"

    def test_rejects_an_empty_name_list(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        with pytest.raises(ValidationError):
            MainDomainCertificate(names=[], certificate_source="acme")

    def test_rejects_duplicate_names(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        with pytest.raises(ValidationError):
            MainDomainCertificate(
                names=["vdi.example.com", "VDI.example.com"],
                certificate_source="acme",
            )

    def test_normalises_names_to_lowercase(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(
            names=["VDI.Example.COM", " alt.example.com "], certificate_source="acme"
        )
        assert cert.names == ["vdi.example.com", "alt.example.com"]

    def test_rejects_more_names_than_a_certificate_can_hold(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        with pytest.raises(ValidationError):
            MainDomainCertificate(
                names=[f"n{i}.example.com" for i in range(101)],
                certificate_source="acme",
            )

    def test_has_no_certificate_data_field(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        # Nothing in the repo reads it, and an unread secret-shaped field is a
        # liability. It arrives with the source that needs it, not before.
        assert "certificate_data" not in MainDomainCertificate.model_fields


# ── Service ──────────────────────────────────────────────────────────────


@pytest.fixture
def stored():
    """The document a configured install already has."""
    return {
        "main_domain": {
            "names": ["vdi.example.com"],
            "certificate_source": "acme",
            "email": "ops@example.com",
            "acme_server": "letsencrypt",
        }
    }


class TestGetCertificates:
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_round_trips_the_stored_document(self, mock_config, stored):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        certs = AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["names"] == ["vdi.example.com"]
        assert certs["main_domain"]["email"] == "ops@example.com"
        assert certs["main_domain"]["acme_server"] == "letsencrypt"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_derives_the_acme_challenge_for_display(self, mock_config, stored):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        certs = AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["acme_challenge"] == "http-01"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_empty_config_is_not_an_error(self, mock_config):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = {}
        assert AdminCertificatesService.get_certificates() == {}


class TestUpdateCertificatesIsNotDestructive:
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_partial_put_keeps_the_acme_account(self, mock_config, stored):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        # The admin saves only the domain name.
        AdminCertificatesService.update_certificates(
            {"main_domain": {"names": ["new.example.com"]}}
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert written["main_domain"]["names"] == ["new.example.com"]
        assert written["main_domain"]["email"] == "ops@example.com"
        assert written["main_domain"]["acme_server"] == "letsencrypt"
        assert written["main_domain"]["certificate_source"] == "acme"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_an_explicit_value_still_wins_over_the_stored_one(
        self, mock_config, stored
    ):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        AdminCertificatesService.update_certificates(
            {"main_domain": {"email": "new@example.com"}}
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert written["main_domain"]["email"] == "new@example.com"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_sibling_blocks_outside_main_domain_survive(self, mock_config):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]},
            "some_future_block": {"kept": True},
        }
        AdminCertificatesService.update_certificates(
            {"main_domain": {"names": ["new.example.com"]}}
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert written["some_future_block"] == {"kept": True}

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_writing_into_an_empty_config_works(self, mock_config):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = {}
        AdminCertificatesService.update_certificates(
            {
                "main_domain": {
                    "names": ["vdi.example.com"],
                    "certificate_source": "acme",
                }
            }
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert written["main_domain"]["names"] == ["vdi.example.com"]


class TestAcmeChallengeIsNeverPersisted:
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_stripped_from_the_payload(self, mock_config, stored):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        AdminCertificatesService.update_certificates(
            {"main_domain": {"names": ["vdi.example.com"], "acme_challenge": "http-01"}}
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert "acme_challenge" not in written["main_domain"]

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_not_resurrected_from_a_previously_stored_value(self, mock_config):
        from api.services.admin.certificates import AdminCertificatesService

        # A document written before the field was stripped.
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"], "acme_challenge": "http-01"}
        }
        AdminCertificatesService.update_certificates(
            {"main_domain": {"names": ["vdi.example.com"]}}
        )
        written = mock_config.replace_certificates_config.call_args.args[0]
        assert "acme_challenge" not in written["main_domain"]

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_the_caller_payload_is_not_mutated_in_place(self, mock_config, stored):
        from api.services.admin.certificates import AdminCertificatesService

        mock_config.get_certificates_config.return_value = stored
        payload = {"main_domain": {"names": ["vdi.example.com"]}}
        AdminCertificatesService.update_certificates(payload)
        # The route passes a freshly dumped model, but a service that mutates
        # its argument is a trap for the next caller that reuses one.
        assert payload == {"main_domain": {"names": ["vdi.example.com"]}}
