# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for registering an acme-dns account and checking its delegation.

These are the two buttons in the certificate panel, and between them they are
the whole setup flow: register, get told which CNAME to ask for, wait, check.

Registering is the dangerous one, and the danger is not obvious. acme-dns has
no update and no delete, so a second registration does not replace the first --
it strands it and hands back a different subdomain. If the customer has already
created the CNAME, it now points at an account this deployment no longer holds
the credentials for, and issuance fails with a DNS error that says nothing
about a button someone pressed twice. So a registration that would overwrite
stored credentials is refused unless the caller says explicitly that it means
to replace them.

Verifying is the safe one and is expected to be run repeatedly while DNS
propagates, so a delegation that is not visible yet is an answer rather than an
error. What it does write is the verified flag, which is the record that the
setup finished -- and it has to be written both ways, because a delegation that
was removed should stop reporting as verified.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def service():
    from api.services.admin import certificates

    return certificates


@pytest.fixture
def registration():
    return {
        "base_url": "https://auth.example.com",
        "username": "eabcdb41-d89f-4580-826f-3e62e9755ef2",
        "password": "htB9mR9DYgcu9bX_afHF62erXaH2TS7bg9KW3F7Z",
        "subdomain": "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
        "fulldomain": "d420c923.auth.example.com",
    }


@pytest.fixture
def configured():
    """A main domain that already has an acme-dns account."""
    return {
        "main_domain": {
            "names": ["vdi.example.com"],
            "certificate_source": "acme_dns",
            "acmedns": {
                "base_url": "https://auth.example.com",
                "username": "an-existing-user",
                "password": "an-existing-password",
                "subdomain": "an-existing-subdomain",
                "fulldomain": "existing.auth.example.com",
                "auto_register": True,
                "verified": True,
            },
        }
    }


def _written(mock_config):
    return mock_config.replace_certificates_config.call_args.args[0]


# ── Registering ──────────────────────────────────────────────────────────


class TestRegister:
    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_stores_what_the_server_returned(
        self, mock_config, mock_acmedns, service, registration
    ):
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }
        mock_acmedns.register.return_value = registration

        service.AdminCertificatesService.register_acmedns("https://auth.example.com")

        acmedns = _written(mock_config)["main_domain"]["acmedns"]
        assert acmedns["username"] == registration["username"]
        assert acmedns["password"] == registration["password"]
        assert acmedns["subdomain"] == registration["subdomain"]
        assert acmedns["fulldomain"] == registration["fulldomain"]

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_returns_the_cname_the_operator_has_to_ask_for(
        self, mock_config, mock_acmedns, service, registration
    ):
        """The one thing the operator has to take away from this call, and it
        involves somebody at another organisation, so it has to be exact."""
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }
        mock_acmedns.register.return_value = registration

        result = service.AdminCertificatesService.register_acmedns(
            "https://auth.example.com"
        )

        assert result["cname_record"] == "_acme-challenge.vdi.example.com"
        assert result["cname_target"] == registration["fulldomain"]

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_never_returns_the_password(
        self, mock_config, mock_acmedns, service, registration
    ):
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }
        mock_acmedns.register.return_value = registration

        result = service.AdminCertificatesService.register_acmedns(
            "https://auth.example.com"
        )

        assert registration["password"] not in str(result)
        assert result["password_set"] is True

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_records_that_the_account_was_auto_registered(
        self, mock_config, mock_acmedns, service, registration
    ):
        """So the panel can show which of the two modes produced what is
        stored, rather than making the operator remember."""
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }
        mock_acmedns.register.return_value = registration

        service.AdminCertificatesService.register_acmedns("https://auth.example.com")
        assert _written(mock_config)["main_domain"]["acmedns"]["auto_register"] is True

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_fresh_registration_is_not_verified(
        self, mock_config, mock_acmedns, service, registration
    ):
        """Nobody has created the CNAME yet: the account was made a second
        ago. Carrying a stale verified flag over would let issuance run
        against a delegation that does not exist."""
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"], "acmedns": {"verified": True}}
        }
        mock_acmedns.register.return_value = registration

        service.AdminCertificatesService.register_acmedns("https://auth.example.com")
        assert _written(mock_config)["main_domain"]["acmedns"]["verified"] is False

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_refuses_to_overwrite_an_account_in_use(
        self, mock_config, mock_acmedns, service, configured
    ):
        """acme-dns has no delete. A second registration strands the first and
        hands back a different subdomain, so the CNAME the customer already
        created now points at an account we no longer hold -- and what surfaces
        is a DNS failure, not a button pressed twice."""
        from api.services.error import Error

        mock_config.get_certificates_config.return_value = configured

        with pytest.raises(Error):
            service.AdminCertificatesService.register_acmedns(
                "https://auth.example.com"
            )

        mock_acmedns.register.assert_not_called()
        mock_config.replace_certificates_config.assert_not_called()

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_replaces_when_told_to(
        self, mock_config, mock_acmedns, service, configured, registration
    ):
        """The way out. Saying so explicitly is the difference between a
        decision and an accident."""
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.register.return_value = registration

        service.AdminCertificatesService.register_acmedns(
            "https://auth.example.com", replace=True
        )

        assert (
            _written(mock_config)["main_domain"]["acmedns"]["username"]
            == registration["username"]
        )

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_failed_registration_stores_nothing(
        self, mock_config, mock_acmedns, service
    ):
        """Half-written credentials are worse than none: they look configured
        and cannot issue."""
        from api.services.error import Error
        from isardvdi_common.helpers.acmedns import AcmeDnsError

        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }
        mock_acmedns.register.side_effect = AcmeDnsError("unreachable")
        mock_acmedns.AcmeDnsError = AcmeDnsError

        # The house error type, not just any exception: a failure that escapes
        # untranslated reaches the operator as a 500 with a stack trace instead
        # of the sentence saying which server could not be reached.
        with pytest.raises(Error) as excinfo:
            service.AdminCertificatesService.register_acmedns(
                "https://auth.example.com"
            )
        assert "unreachable" in str(excinfo.value)

        mock_config.replace_certificates_config.assert_not_called()

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_needs_a_name_to_build_the_cname_for(
        self, mock_config, mock_acmedns, service
    ):
        """Without a configured domain there is nothing to tell the operator to
        delegate, and registering would strand an account immediately."""
        from api.services.error import Error

        mock_config.get_certificates_config.return_value = {}

        with pytest.raises(Error):
            service.AdminCertificatesService.register_acmedns(
                "https://auth.example.com"
            )

        mock_acmedns.register.assert_not_called()


# ── Verifying ────────────────────────────────────────────────────────────


class TestVerify:
    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_checks_the_stored_delegation(
        self, mock_config, mock_acmedns, service, configured
    ):
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.verify_cname.return_value = {"verified": True, "message": "ok"}

        service.AdminCertificatesService.verify_acmedns()

        mock_acmedns.verify_cname.assert_called_once_with(
            "vdi.example.com", "existing.auth.example.com"
        )

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_successful_check_is_recorded(
        self, mock_config, mock_acmedns, service, configured
    ):
        configured["main_domain"]["acmedns"]["verified"] = False
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.verify_cname.return_value = {"verified": True, "message": "ok"}

        service.AdminCertificatesService.verify_acmedns()
        assert _written(mock_config)["main_domain"]["acmedns"]["verified"] is True

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_delegation_that_went_away_stops_being_verified(
        self, mock_config, mock_acmedns, service, configured
    ):
        """Written both ways on purpose. A flag that only ever goes true is a
        record of something that was once true, which is not what anything
        reading it wants to know."""
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.verify_cname.return_value = {
            "verified": False,
            "message": "not visible",
        }

        service.AdminCertificatesService.verify_acmedns()
        assert _written(mock_config)["main_domain"]["acmedns"]["verified"] is False

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_negative_result_is_returned_not_raised(
        self, mock_config, mock_acmedns, service, configured
    ):
        """This gets pressed repeatedly while DNS propagates. An exception per
        attempt is noise, and the message is the useful part."""
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.verify_cname.return_value = {
            "verified": False,
            "message": "not visible from system yet",
        }

        result = service.AdminCertificatesService.verify_acmedns()
        assert result["verified"] is False
        assert "not visible" in result["message"]

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_verifying_without_a_registration_is_refused(
        self, mock_config, mock_acmedns, service
    ):
        """There is nothing to compare a delegation against, and a check that
        cannot fail would report the domain as ready to issue."""
        from api.services.error import Error

        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"]}
        }

        with pytest.raises(Error):
            service.AdminCertificatesService.verify_acmedns()

        mock_acmedns.verify_cname.assert_not_called()

    @patch("api.services.admin.certificates.acmedns")
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_verifying_never_returns_the_password(
        self, mock_config, mock_acmedns, service, configured
    ):
        mock_config.get_certificates_config.return_value = configured
        mock_acmedns.verify_cname.return_value = {"verified": True, "message": "ok"}

        result = service.AdminCertificatesService.verify_acmedns()
        assert "an-existing-password" not in str(result)
