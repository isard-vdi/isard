# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for storing acme-dns credentials in the main-domain certificate config.

The credentials sit in the database in the clear, alongside every other
credential this product keeps there. What they do NOT do is travel back to the
browser: the GET reports whether a password is stored and never what it is.

Those two are not in tension, they are about different exposures. A value in
the database is read by whoever can read the database. A value in a GET
response is in the browser's history, in the logs of any proxy in between, and
in whatever an operator screenshots -- places the rest of this product's
credentials do not reach. Not sending it is not encryption; it is declining to
make the exposure wider than it has to be, and it is what the two existing
helpers for LDAP and provider secrets already do.

Declining to send it forces the other half: a PUT that arrives with the
password blank has to mean "keep the stored one", because the form cannot
resend what it was never given. Blank with nothing stored is the case the two
existing helpers disagree about -- one raises as required, the other drops the
key silently. For acme-dns it is required: without the password there is no
issuance at all, so accepting the save would store a configuration that cannot
work and report success.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError


@pytest.fixture
def service():
    from api.services.admin import certificates

    return certificates


@pytest.fixture
def stored():
    """A main domain already configured for acme-dns."""
    return {
        "main_domain": {
            "names": ["vdi.example.com"],
            "certificate_source": "acme_dns",
            "acme_server": "letsencrypt",
            "acmedns": {
                "base_url": "https://auth.example.com",
                "username": "eabcdb41-d89f-4580-826f-3e62e9755ef2",
                "password": "not-a-real-password-for-tests-0123456789",
                "subdomain": "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
                "fulldomain": "d420c923.auth.example.com",
                "auto_register": True,
                "verified": True,
            },
        }
    }


# ── Schema ───────────────────────────────────────────────────────────────


class TestSchema:
    def test_the_credentials_are_accepted(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(
            names=["vdi.example.com"],
            certificate_source="acme_dns",
            acmedns={
                "base_url": "https://auth.example.com",
                "username": "a-user",
                "password": "a-password",
                "subdomain": "a-subdomain",
            },
        )
        assert cert.acmedns.username == "a-user"

    def test_dns01_is_a_challenge_this_release_knows(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(acme_challenge="dns-01")
        assert cert.acme_challenge == "dns-01"

    def test_an_unknown_challenge_is_still_refused(self):
        from api.schemas.admin.certificates import MainDomainCertificate

        with pytest.raises(ValidationError):
            MainDomainCertificate(acme_challenge="tls-alpn-01")

    def test_a_partial_credential_set_is_allowed_through_the_schema(self):
        """Deliberately. The operator fills this form one field at a time, and
        a schema that refused three of four would reject the payload the
        auto-register flow sends before it has a password."""
        from api.schemas.admin.certificates import MainDomainCertificate

        cert = MainDomainCertificate(
            certificate_source="acme_dns",
            acmedns={"base_url": "https://auth.example.com"},
        )
        assert cert.acmedns.base_url == "https://auth.example.com"


# ── Reading ──────────────────────────────────────────────────────────────


class TestGet:
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_the_password_never_leaves(self, mock_config, service, stored):
        mock_config.get_certificates_config.return_value = stored
        certs = service.AdminCertificatesService.get_certificates()
        assert "password" not in certs["main_domain"]["acmedns"]

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_reports_that_one_is_stored(self, mock_config, service, stored):
        """The form needs to tell "leave blank to keep it" from "there is
        nothing to keep", and those want different words on screen."""
        mock_config.get_certificates_config.return_value = stored
        certs = service.AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["acmedns"]["password_set"] is True

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_it_reports_when_none_is_stored(self, mock_config, service, stored):
        stored["main_domain"]["acmedns"].pop("password")
        mock_config.get_certificates_config.return_value = stored
        certs = service.AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["acmedns"]["password_set"] is False

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_the_rest_of_the_credentials_are_returned(
        self, mock_config, service, stored
    ):
        """The operator has to be able to see which acme-dns account is in use,
        and the CNAME target is what they ask their customer to create."""
        mock_config.get_certificates_config.return_value = stored
        acmedns = service.AdminCertificatesService.get_certificates()["main_domain"][
            "acmedns"
        ]
        assert acmedns["base_url"] == "https://auth.example.com"
        assert acmedns["username"] == "eabcdb41-d89f-4580-826f-3e62e9755ef2"
        assert acmedns["fulldomain"] == "d420c923.auth.example.com"
        assert acmedns["verified"] is True

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_the_challenge_is_derived_as_dns01(self, mock_config, service, stored):
        mock_config.get_certificates_config.return_value = stored
        certs = service.AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["acme_challenge"] == "dns-01"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_reading_does_not_mutate_what_is_stored(self, mock_config, service, stored):
        """Stripping the password has to happen on the way out, not in the
        document the accessor handed over -- that one is a cache entry, and
        emptying it would take the password away from the issuance path."""
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.get_certificates()
        assert stored["main_domain"]["acmedns"]["password"]

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_deployment_without_acme_dns_is_unaffected(self, mock_config, service):
        mock_config.get_certificates_config.return_value = {
            "main_domain": {"names": ["vdi.example.com"], "certificate_source": "acme"}
        }
        certs = service.AdminCertificatesService.get_certificates()
        assert certs["main_domain"]["acme_challenge"] == "http-01"
        assert "acmedns" not in certs["main_domain"]


# ── Writing ──────────────────────────────────────────────────────────────


def _written(mock_config):
    return mock_config.replace_certificates_config.call_args.args[0]


class TestUpdate:
    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_blank_password_keeps_the_stored_one(self, mock_config, service, stored):
        """The reason the rule exists at all: the form was never given the
        password, so it cannot send it back, and the write replaces the whole
        subtree."""
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"password": ""}}}
        )
        assert (
            _written(mock_config)["main_domain"]["acmedns"]["password"]
            == "not-a-real-password-for-tests-0123456789"
        )

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_an_omitted_password_keeps_the_stored_one(
        self, mock_config, service, stored
    ):
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"username": "a-new-user"}}}
        )
        acmedns = _written(mock_config)["main_domain"]["acmedns"]
        assert acmedns["password"] == "not-a-real-password-for-tests-0123456789"
        assert acmedns["username"] == "a-new-user"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_supplied_password_replaces_the_stored_one(
        self, mock_config, service, stored
    ):
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"password": "a-rotated-password"}}}
        )
        assert (
            _written(mock_config)["main_domain"]["acmedns"]["password"]
            == "a-rotated-password"
        )

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_blank_password_with_nothing_stored_is_refused(
        self, mock_config, service
    ):
        """Without it there is no issuance, so accepting the save would store a
        configuration that cannot work and report success. The two existing
        helpers disagree here; this field is the required kind."""
        from api.services.error import Error

        mock_config.get_certificates_config.return_value = {}
        with pytest.raises(Error):
            service.AdminCertificatesService.update_certificates(
                {
                    "main_domain": {
                        "certificate_source": "acme_dns",
                        "acmedns": {
                            "base_url": "https://auth.example.com",
                            "username": "a-user",
                            "password": "",
                            "subdomain": "a-subdomain",
                        },
                    }
                }
            )
        mock_config.replace_certificates_config.assert_not_called()

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_a_blank_password_is_not_required_for_another_source(
        self, mock_config, service
    ):
        """An operator moving back to HTTP-01 still has the acme-dns fields on
        the form, and the password one is blank because it never came down.
        Demanding it there would block a save that has nothing to do with
        acme-dns, on the one path where the credential is being abandoned."""
        mock_config.get_certificates_config.return_value = {}
        service.AdminCertificatesService.update_certificates(
            {
                "main_domain": {
                    "names": ["vdi.example.com"],
                    "certificate_source": "acme",
                    "acmedns": {"base_url": "https://auth.example.com", "password": ""},
                }
            }
        )
        mock_config.replace_certificates_config.assert_called_once()
        written = _written(mock_config)["main_domain"]["acmedns"]
        assert "password" not in written, "an empty secret is worse than none"

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_password_set_never_reaches_the_database(
        self, mock_config, service, stored
    ):
        """It is derived on read, like acme_challenge. Persisting it would make
        a second source of truth that can disagree with the first."""
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"password_set": True, "username": "u"}}}
        )
        assert "password_set" not in _written(mock_config)["main_domain"]["acmedns"]

    @patch("api.services.admin.certificates.CertificatesConfig")
    def test_the_rest_of_the_credentials_survive_a_partial_save(
        self, mock_config, service, stored
    ):
        """The write replaces the whole subtree, so anything the form did not
        render has to be merged back or it is gone."""
        mock_config.get_certificates_config.return_value = stored
        service.AdminCertificatesService.update_certificates(
            {"main_domain": {"acmedns": {"username": "a-new-user"}}}
        )
        acmedns = _written(mock_config)["main_domain"]["acmedns"]
        assert acmedns["fulldomain"] == "d420c923.auth.example.com"
        assert acmedns["subdomain"] == "d420c923-bbd7-4056-ab64-c3ca54c9b3cf"
