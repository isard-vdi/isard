#
#   Copyright © 2026 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Structural tests for the main-domain certificate panel in the admin webapp.

Same approach as the desktop storage modal suite next door: the panel is
template plus jQuery, so these read the sources and assert the contract pieces
are present. A richer test would need the whole Jinja2 loader chain and the
auth-aware render wrapper, which buys little for front-end-only changes.

Two of these are not cosmetic:

* the panel must sit behind an admin-only guard, because it configures the
  certificate the whole deployment is served with, while the sibling
  per-category branding UI is reachable by managers;
* the save must not drop names it did not render. The API stores an ordered
  list, this release only edits the first entry, and a form that posts
  ``[the one field]`` would silently truncate a certificate that carries more.
"""

import re
from pathlib import Path

import pytest

WEBAPP_ROOT = Path(__file__).resolve().parents[1] / "webapp"
DOMAINS_PAGE = WEBAPP_ROOT / "templates" / "admin" / "pages" / "domains_resources.html"
DOMAINS_MODALS = (
    WEBAPP_ROOT / "templates" / "admin" / "pages" / "domains_resources_modals.html"
)
DOMAINS_JS = WEBAPP_ROOT / "static" / "admin" / "js" / "domains_resources.js"
BRANDING_SNIPPET = (
    WEBAPP_ROOT / "templates" / "snippets" / "category_branding_fields.html"
)
CATEGORIES_JS = WEBAPP_ROOT / "static" / "admin" / "js" / "categories_management.js"


@pytest.fixture(scope="module")
def domains_page() -> str:
    return DOMAINS_PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def domains_modals() -> str:
    return DOMAINS_MODALS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def domains_js() -> str:
    return DOMAINS_JS.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# domains_resources.html — the panel
# ──────────────────────────────────────────────────────────────────────


class TestCertificatesPanel:
    def test_panel_exists(self, domains_page):
        assert 'id="CertificatesConfig"' in domains_page

    def test_panel_has_a_status_label_and_an_edit_button(self, domains_page):
        assert 'id="certificatesStatusLabel"' in domains_page
        assert 'id="btn-edit-certificates"' in domains_page

    def test_panel_is_admin_only(self, domains_page):
        """The deployment certificate is not a per-category manager concern."""
        guard = re.search(
            r"\{%\s*if\s+current_user\.role\s*==\s*'admin'\s*%\}(.*?)\{%\s*endif\s*%\}",
            domains_page,
            re.DOTALL,
        )
        assert guard, "no admin-only block found in the page"
        assert 'id="CertificatesConfig"' in guard.group(1)


# ──────────────────────────────────────────────────────────────────────
# domains_resources_modals.html — the modal
# ──────────────────────────────────────────────────────────────────────


class TestCertificatesModal:
    def test_modal_exists(self, domains_modals):
        assert 'id="modalEditCertificates"' in domains_modals
        assert 'id="modalEditCertificatesForm"' in domains_modals

    def test_has_the_fields_this_release_edits(self, domains_modals):
        for field in (
            'id="cert-name"',
            'id="cert-source"',
            'id="cert-email"',
            'id="cert-acme-server"',
        ):
            assert field in domains_modals, field

    def test_offers_only_the_sources_the_api_accepts(self, domains_modals):
        source = domains_modals.split('id="cert-source"', 1)[1].split("</select>", 1)[0]
        assert 'value="acme"' in source
        assert 'value="acme_dns"' in source
        # The schema is Literal["acme", "acme_dns"]; offering anything else
        # would produce a form that fails validation on save. "custom" is the
        # one that is still out.
        assert 'value="custom"' not in source

    def test_has_the_acme_dns_form(self, domains_modals):
        assert "cert-acmedns" in domains_modals


# ──────────────────────────────────────────────────────────────────────
# domains_resources.js — the wiring
# ──────────────────────────────────────────────────────────────────────


class TestCertificatesJs:
    def test_talks_to_the_admin_certificates_endpoint(self, domains_js):
        assert "/api/v4/admin/config/certificates" in domains_js

    def test_loads_the_status_only_when_the_panel_is_rendered(self, domains_js):
        """A manager never receives the panel, so the GET must not fire for them."""
        assert 'if ($("#CertificatesConfig").length)' in domains_js

    def test_saves_with_a_put(self, domains_js):
        block = domains_js.split('$("#modalEditCertificates #send")', 1)
        assert len(block) == 2, "no save handler for the certificates modal"
        assert 'type: "PUT"' in block[1].split("});")[0] or '"PUT"' in block[1][:800]

    def test_sends_the_domain_as_a_list(self, domains_js):
        """The stored shape is an ordered list; names[0] is the primary."""
        assert "names:" in domains_js

    def test_preserves_names_it_does_not_render(self, domains_js):
        """This release edits the primary only. A certificate that carries more
        names must not lose them because the form has a single input."""
        assert "certExtraNames" in domains_js

    def test_sends_the_acme_account(self, domains_js):
        assert "email:" in domains_js
        assert "acme_server:" in domains_js


# ──────────────────────────────────────────────────────────────────────
# Per-category branding — label only
# ──────────────────────────────────────────────────────────────────────


class TestBrandingSnippet:
    def test_acme_option_names_the_challenge(self):
        """Two ACME challenge types are coming; "ACME" alone stops being
        unambiguous the moment the second one lands."""
        snippet = BRANDING_SNIPPET.read_text(encoding="utf-8")
        assert '"acme": "ACME HTTP-01 (Let\'s Encrypt)"' in snippet

    def test_no_acme_dns_option_yet(self):
        snippet = BRANDING_SNIPPET.read_text(encoding="utf-8")
        assert "acme_dns" not in snippet

    def test_categories_js_keeps_its_existing_trigger(self):
        """main already fires the change handler on open, so the per-category
        modal renders its custom-certificate form correctly. Nothing to add
        here, and re-adding it would double-fire the handler."""
        js = CATEGORIES_JS.read_text(encoding="utf-8")
        handler = js.split("branding[domain][certificate_source]", 1)[1]
        assert handler.split("}).trigger(")[0].count('.trigger("change")') == 0
        assert '.trigger("change")' in handler[:600]
