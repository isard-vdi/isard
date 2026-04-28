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

"""Smoke tests for the per-row Storage actions consolidation in the
admin storage list.

Locks down the contract that ``detailButtons()`` renders a *single*
trigger button rather than a cluster of inline action buttons, and that
the trigger opens the existing ``#modalSearchStorage`` modal — the
single place that holds the info + actions UI.
"""

from pathlib import Path

import pytest

WEBAPP_ROOT = Path(__file__).resolve().parents[1] / "webapp"
STORAGE_JS = WEBAPP_ROOT / "static" / "admin" / "js" / "storage.js"
STORAGE_MODALS = WEBAPP_ROOT / "templates" / "admin" / "pages" / "storage_modals.html"


@pytest.fixture(scope="module")
def storage_js() -> str:
    return STORAGE_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def storage_modals_html() -> str:
    return STORAGE_MODALS.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# detailButtons() now renders one button, not a cluster
# ──────────────────────────────────────────────────────────────────────


def test_detail_buttons_renders_single_storage_actions_button(storage_js: str) -> None:
    detail_fn = _slice(storage_js, "function detailButtons(")
    # The single trigger we added:
    assert "btn-storage-actions" in detail_fn
    # Inline action buttons that used to live in the same panel must be
    # gone — leaving them would re-introduce the multi-button clutter
    # the refactor is meant to remove.
    forbidden_inline = (
        '"btn-success btn-xs btn-move"',
        '"btn-primary btn-xs btn-virt_win_reg"',
        '"btn-info btn-xs btn-increase"',
        '"btn-info btn-xs btn-create"',
        '"btn-info btn-xs btn-sparsify"',
        '"btn-info btn-xs btn-disconnect"',
    )
    for token in forbidden_inline:
        assert token not in detail_fn, f"detailButtons must not render {token}"


def test_detail_buttons_only_renders_when_storage_is_ready(storage_js: str) -> None:
    """The cluster-of-buttons panel was guarded by ``status == 'ready'``.
    The single-button replacement must keep that guard so a half-broken
    chain doesn't expose actions that the apiv4 layer would reject."""
    detail_fn = _slice(storage_js, "function detailButtons(")
    assert (
        'storage.status != "ready"' in detail_fn
        or 'storage.status == "ready"' in detail_fn
    )


def test_storage_actions_handler_opens_search_modal(storage_js: str) -> None:
    """The new handler must delegate to ``openStorageSearchModal`` so we
    keep one source of truth for storage-actions UI rather than
    duplicating the modal."""
    handler = _slice(storage_js, "'.btn-storage-actions'")
    assert "openStorageSearchModal" in handler


# ──────────────────────────────────────────────────────────────────────
# The shared modal still exposes the full action set
# ──────────────────────────────────────────────────────────────────────


def test_search_modal_still_contains_action_buttons(storage_modals_html: str) -> None:
    """``#modalSearchStorage`` is the only place the per-row Storage
    actions trigger opens, so the action buttons must remain there.
    Sanity-check that the panel and its eight buttons are still wired."""
    modal = _slice(storage_modals_html, 'id="modalSearchStorage"', length=8000)
    assert 'id="storage-action-buttons"' in modal
    for css_class in (
        "btn-modal-move",
        "btn-modal-virt_win_reg",
        "btn-modal-increase",
        "btn-modal-create",
        "btn-modal-sparsify",
        "btn-modal-disconnect",
        "btn-modal-find",
        "btn-modal-delete",
    ):
        assert css_class in modal, f"missing action class {css_class}"


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _slice(source: str, anchor: str, length: int = 4000) -> str:
    idx = source.find(anchor)
    assert idx != -1, f"anchor not found in source: {anchor!r}"
    return source[idx : idx + length]
