# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the acme-dns half of the main-domain certificate panel.

These are source checks, like the rest of this file's neighbours: the admin
panel is Jinja plus jQuery with no test harness, so what can be pinned is that
the markup and the wiring say what they are supposed to say. That is worth
doing for exactly the parts where being wrong is silent.

Three of those.

The password field must never be filled from the GET, because the GET does not
carry it. What the form has instead is a flag, and the hint has to distinguish
"a password is stored, leaving this blank keeps it" from "there is nothing
stored", which look identical on screen and mean opposite things.

The save must not send an empty password key. The API reads a blank as "keep
the stored one", which is right, but sending the key when nothing is stored
turns an unrelated save into a required-field error on a form the operator
never meant to fill in.

Registering must ask before replacing. acme-dns cannot delete an account, so a
second registration abandons the first, and the CNAME the domain owner already
created stops working. A confirm() is the difference between a decision and a
double click, and it is the only thing standing between the two here.
"""

import pathlib

import pytest

WEBAPP = pathlib.Path(__file__).resolve().parents[1] / "webapp"
MODALS = WEBAPP / "templates" / "admin" / "pages" / "domains_resources_modals.html"
DOMAINS_JS = WEBAPP / "static" / "admin" / "js" / "domains_resources.js"


@pytest.fixture
def modals():
    return MODALS.read_text(encoding="utf-8")


@pytest.fixture
def js():
    return DOMAINS_JS.read_text(encoding="utf-8")


# ── The form ─────────────────────────────────────────────────────────────


class TestForm:
    def test_it_has_every_credential_field(self, modals):
        for field in (
            'id="cert-acmedns-base-url"',
            'id="cert-acmedns-username"',
            'id="cert-acmedns-password"',
            'id="cert-acmedns-subdomain"',
            'id="cert-acmedns-fulldomain"',
        ):
            assert field in modals, field

    def test_the_password_field_is_a_password_field(self, modals):
        block = modals.split('id="cert-acmedns-password"', 1)[1].split(">", 1)[0]
        assert 'type="password"' in block

    def test_the_password_field_does_not_autofill(self, modals):
        """A browser offering the operator's own saved password here would put
        an unrelated secret into an acme-dns account."""
        block = modals.split('id="cert-acmedns-password"', 1)[1].split(">", 1)[0]
        assert 'autocomplete="new-password"' in block

    def test_it_offers_both_modes(self, modals):
        mode = modals.split('id="cert-acmedns-mode"', 1)[1].split("</select>", 1)[0]
        assert 'value="auto"' in mode
        assert 'value="manual"' in mode

    def test_the_acme_dns_form_starts_hidden(self, modals):
        """Most deployments are on HTTP-01 and never touch this."""
        block = modals.split('id="cert-acmedns-form"', 1)[1].split(">", 1)[0]
        assert "display: none" in block

    def test_it_shows_the_cname_the_owner_has_to_create(self, modals):
        assert 'id="cert-acmedns-cname-record"' in modals
        assert 'id="cert-acmedns-cname-target"' in modals

    def test_the_cname_block_says_issuance_depends_on_it(self, modals):
        """The operator has to ask somebody at another organisation for this,
        which does not happen unless the screen says it is required."""
        block = modals.split('id="cert-acmedns-cname-alert"', 1)[1].split("</div>", 1)[
            0
        ]
        assert "cannot work" in block

    def test_the_register_button_warns_before_it_is_pressed(self, modals):
        """acme-dns cannot delete an account. The consequence belongs next to
        the button, not only in the confirmation after it."""
        block = modals.split('id="cert-acmedns-auto-actions"', 1)[1].split(
            'id="cert-acmedns-username"', 1
        )[0]
        assert "abandons the first" in block

    def test_there_is_a_way_to_check_the_delegation(self, modals):
        assert 'id="cert-acmedns-verify"' in modals


# ── The wiring ───────────────────────────────────────────────────────────


class TestWiring:
    def test_it_calls_the_register_endpoint(self, js):
        assert "/api/v4/admin/config/certificates/acmedns/register" in js

    def test_it_calls_the_verify_endpoint(self, js):
        assert "/api/v4/admin/config/certificates/acmedns/verify" in js

    def test_registering_asks_before_replacing(self, js):
        """The only thing between a decision and a double click."""
        block = js.split('$("#cert-acmedns-register")', 1)[1].split(
            '$("#cert-acmedns-verify")', 1
        )[0]
        assert "confirm(" in block
        assert "replace" in block

    def test_it_does_not_send_replace_unasked(self, js):
        block = js.split('$("#cert-acmedns-register")', 1)[1].split(
            '$("#cert-acmedns-verify")', 1
        )[0]
        assert "replace: true" not in block, "replacing must come from the confirmation"

    def test_the_password_is_only_sent_when_typed(self, js):
        """An empty key would be read as "keep the stored one", which is right,
        but sending it with nothing stored makes an unrelated save fail as a
        required field."""
        block = js.split("function certAcmeDnsPayload", 1)[1].split("\n    }", 1)[0]
        assert "if (password)" in block

    def test_the_form_is_hidden_unless_the_source_is_acme_dns(self, js):
        assert "certToggleAcmeDns" in js
        block = js.split("function certToggleAcmeDns", 1)[1].split("\n    }", 1)[0]
        assert '"acme_dns"' in block

    def test_the_auto_actions_follow_the_mode(self, js):
        block = js.split("function certToggleAcmeDns", 1)[1].split("\n    }", 1)[0]
        assert "cert-acmedns-auto-actions" in block

    def test_opening_the_modal_never_fills_the_password(self, js):
        """It is not in the response. Filling it from anything would be
        inventing a secret."""
        block = js.split('$("#btn-edit-certificates")', 1)[1].split(
            '$("#modalEditCertificates #send")', 1
        )[0]
        assert '$("#cert-acmedns-password").val(acmedns' not in block

    def test_the_hint_distinguishes_stored_from_absent(self, js):
        block = js.split("function certShowPasswordHint", 1)[1].split("\n    }", 1)[0]
        assert "leave blank to keep it" in block
        assert "No password stored yet" in block

    def test_the_save_carries_the_credentials(self, js):
        block = js.split('$("#modalEditCertificates #send")', 1)[1]
        assert "acmedns: certAcmeDnsPayload()" in block

    def test_a_delegation_that_is_not_there_is_not_reported_as_an_error(self, js):
        """It gets pressed while DNS propagates; a red failure per attempt
        would train the operator to ignore it."""
        block = js.split('$("#cert-acmedns-verify")', 1)[1].split(
            '$("#btn-edit-certificates")', 1
        )[0]
        # Delimited by the error handler itself, not by the word: the comment
        # above the success handler contains it too.
        success = block.split("error: function", 1)[0]
        assert "data.verified" in success
        # And the message has to reach the screen. Reporting only that the
        # check ran would leave the operator without the one sentence that
        # says whether to wait or to go fix the record.
        assert "data.message" in success

    def test_the_status_line_says_whether_the_delegation_is_verified(self, js):
        """Whether it is in place decides whether issuance can work at all, so
        it belongs in the line shown without opening anything."""
        block = js.split("function loadCertificatesStatus", 1)[1].split("\n    }", 1)[0]
        assert "acme_dns" in block
        assert "verified" in block
