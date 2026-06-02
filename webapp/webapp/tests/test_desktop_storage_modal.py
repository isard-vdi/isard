#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Smoke tests for the Desktop Storage modal added to the admin webapp.

The modal lives entirely in static template + jQuery code, so these tests
read the source files and assert that the contract pieces are present.
They are deliberately structural — a richer integration test would have
to set up the full Jinja2 environment (with the template loader chain
and the auth-aware ``render_webapp`` wrapper), which is out of scope for
these front-end-only changes.
"""

from pathlib import Path

import pytest

WEBAPP_ROOT = Path(__file__).resolve().parents[1] / "webapp"
DESKTOPS_MODALS = WEBAPP_ROOT / "templates" / "pages" / "desktops_modals.html"
DESKTOPS_PAGE = WEBAPP_ROOT / "templates" / "admin" / "pages" / "desktops.html"
DESKTOPS_JS = WEBAPP_ROOT / "static" / "admin" / "js" / "desktops.js"


@pytest.fixture(scope="module")
def desktops_modals_html() -> str:
    return DESKTOPS_MODALS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def desktops_page_html() -> str:
    return DESKTOPS_PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def desktops_js() -> str:
    return DESKTOPS_JS.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# desktops_modals.html — new <div id="modalDesktopStorage"> wrapper
# ──────────────────────────────────────────────────────────────────────


def test_desktops_modals_contains_storage_modal(desktops_modals_html: str) -> None:
    assert 'id="modalDesktopStorage"' in desktops_modals_html
    # Title slot the JS populates with the desktop name.
    assert 'class="modal-title-name"' in desktops_modals_html
    # Body container the JS appends storage rows into.
    assert 'id="desktop-storage-list"' in desktops_modals_html


def test_desktops_modals_storage_modal_has_close_button(
    desktops_modals_html: str,
) -> None:
    """Bootstrap-3 dismiss control must exist so the modal is usable
    even when the JS handler errors out before populating the body."""
    storage_modal = _slice(desktops_modals_html, 'id="modalDesktopStorage"')
    assert 'data-dismiss="modal"' in storage_modal


# ──────────────────────────────────────────────────────────────────────
# desktops.js — new btn-storage trigger + click handler
# ──────────────────────────────────────────────────────────────────────


def test_desktops_js_renders_storage_button_for_stopped_desktops(
    desktops_js: str,
) -> None:
    """The Storage button is appended to the existing Start button on
    Stopped desktops only — Maintenance keeps its own ``btn-cancel``."""
    assert "renderStorageActionsButton" in desktops_js
    assert 'id="btn-storage"' in desktops_js
    # Renders only on Stopped — sanity check that the helper isn't
    # called from the Maintenance branch (which has its own btn-cancel).
    stopped_branch = _slice(desktops_js, "if(status=='Stopped')")
    assert "renderStorageActionsButton(data)" in stopped_branch


def test_desktops_js_has_btn_storage_case(desktops_js: str) -> None:
    """``case 'btn-storage'`` must dispatch into the modal opener so the
    DataTable click delegate routes the click to our code."""
    assert "case 'btn-storage'" in desktops_js
    assert "openDesktopStorageModal(data)" in desktops_js


def test_desktops_js_open_modal_uses_admin_storage_endpoint(
    desktops_js: str,
) -> None:
    """The modal must fetch storage IDs via the admin scope so manager
    category-scoping is enforced server-side, matching the existing
    Maintenance-row btn-cancel flow."""
    open_fn = _slice(desktops_js, "function openDesktopStorageModal(")
    assert "/api/v4/admin/item/domain/storage/" in open_fn
    assert "modalDesktopStorage" in open_fn


def test_desktops_js_increase_button_delegates_to_shared_handler(
    desktops_js: str,
) -> None:
    """Increase must reuse storage.js ``.btn-increase``, not ``window.prompt()``."""
    assert "btn-desktop-storage-increase" not in desktops_js
    assert "window.prompt(" not in desktops_js
    assert 'class="btn btn-info btn-xs btn-increase"' in desktops_js


def test_desktops_modals_includes_shared_increase_snippet(
    desktops_modals_html: str,
) -> None:
    """The shared #modalIncreaseStorage snippet must be included for the handler to find a modal."""
    assert "/snippets/storage_increase_modal.html" in desktops_modals_html


def test_desktops_page_loads_storage_increase_script(
    desktops_page_html: str,
) -> None:
    """desktops.html must load both the helpers and the increase-specific handler."""
    assert "admin/js/storage_actions.js" in desktops_page_html
    assert "admin/js/storage_increase.js" in desktops_page_html
    # storage_actions.js defines performStorageOperation — must load first.
    assert desktops_page_html.index("storage_actions.js") < desktops_page_html.index(
        "storage_increase.js"
    )


def test_desktops_js_cancel_handler_calls_abort_operations(
    desktops_js: str,
) -> None:
    handler = _slice(desktops_js, "'.btn-desktop-storage-cancel'")
    assert "/abort-operations" in handler


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _slice(source: str, anchor: str, length: int = 4000) -> str:
    """Return the chunk of ``source`` immediately following ``anchor``.

    Lets each assertion focus on a specific function/branch instead of
    matching across the whole file (which would silently pass if the
    pattern existed somewhere unrelated).
    """
    idx = source.find(anchor)
    assert idx != -1, f"anchor not found in source: {anchor!r}"
    return source[idx : idx + length]
