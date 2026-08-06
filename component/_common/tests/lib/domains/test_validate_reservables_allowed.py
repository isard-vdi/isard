#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Authorization regression test for ``validate_reservables_vgpus``.

A user without permission over a vGPU reservable (its ``allowed`` field) was
able to *attach* that profile to a desktop through the edit path
(``PUT /item/desktop/{id}/edit`` → ``update_desktop`` →
``validate_reservables_vgpus``), which validated existence/duplicates/hypervisor
but not ``allowed``. Booking and start never re-check ``allowed`` (they consume
whatever is attached), so the profile then reached the engine. This test pins
the attach-time allowlist enforcement centralised in
``validate_reservables_vgpus``:

  * a caller newly attaching a NOT-allowed profile → ``forbidden``
    (``reservable_not_allowed``);
  * an allowed caller (allowlist returns the id) → accepted;
  * a profile already present on the desktop (``existing_vgpus``) → exempt;
  * ``payload=None`` (internal/legacy callers) → no enforcement.

Without the enforcement branch, the first case does NOT raise and the test fails.
"""

from unittest.mock import MagicMock

import pytest

RESID = "NVIDIA-TESTGPU-4Q"


@pytest.fixture
def mod(monkeypatch):
    from isardvdi_common.lib.domains.desktops import desktops as m

    # Existence query: r.table("reservables_vgpus").get_all(...).pluck(...).run()
    class _Q:
        def get_all(self, *a, **k):
            return self

        def pluck(self, *a, **k):
            return self

        def run(self, conn):
            return [{"id": RESID, "model": "NVIDIA-TESTGPU"}]

    monkeypatch.setattr(
        m.r, "table", lambda name: _Q() if name == "reservables_vgpus" else MagicMock()
    )
    monkeypatch.setattr(m.r, "args", lambda x: x, raising=False)

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        m.DesktopsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(m.DesktopsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    return m


def _set_allowlist(monkeypatch, mod, ids):
    monkeypatch.setattr(
        mod.Alloweds,
        "get_items_allowed",
        classmethod(lambda cls, payload, table, **k: [{"id": i} for i in ids]),
    )


def test_attach_not_allowed_is_forbidden(mod, monkeypatch):
    _set_allowlist(monkeypatch, mod, [])  # user is allowed NOTHING
    payload = {"user_id": "u", "role_id": "user", "category_id": "b", "group_id": "b-b"}
    with pytest.raises(mod.Error) as exc:
        mod.validate_reservables_vgpus([RESID], payload=payload)
    assert exc.value.error["description_code"] == "reservable_not_allowed"


def test_attach_allowed_ok(mod, monkeypatch):
    _set_allowlist(monkeypatch, mod, [RESID])  # user IS allowed
    payload = {"user_id": "u", "role_id": "user", "category_id": "a", "group_id": "a-a"}
    assert mod.validate_reservables_vgpus([RESID], payload=payload) == [RESID]


def test_existing_profile_is_exempt(mod, monkeypatch):
    _set_allowlist(monkeypatch, mod, [])  # allowed nothing, but already attached
    payload = {"user_id": "u", "role_id": "user", "category_id": "b", "group_id": "b-b"}
    assert mod.validate_reservables_vgpus(
        [RESID], payload=payload, existing_vgpus=[RESID]
    ) == [RESID]


def test_no_payload_no_enforcement(mod, monkeypatch):
    # Legacy/internal callers pass no payload — existence still checked, but the
    # allowlist is not consulted (would raise if it were, since allowlist=[]).
    _set_allowlist(monkeypatch, mod, [])
    assert mod.validate_reservables_vgpus([RESID]) == [RESID]
