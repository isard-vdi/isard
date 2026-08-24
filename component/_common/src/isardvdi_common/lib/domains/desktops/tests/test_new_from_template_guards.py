#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Precondition guards on ``DesktopsProcessed.new_from_template``.

These are the ``raise Error(...)`` gates that reject an unbuildable
desktop before it is ever inserted. A guard that silently stops firing is
invisible until a user creates a desktop they should not be able to
create — so each of these is pinned to the exact ``Error`` type and
``description_code`` the real code raises.

The function under test is NEVER mocked: every collaborator it leans on
(the ``Caches`` document lookups, ``merge_new_data_with_template``, the
hardware/media helpers, the ``DesktopFromTemplate`` schema) is stubbed,
but the guard decision is taken by the production code.

Guards pinned (line numbers on ``origin/main``):
* template not found                       (L556) -> not_found
* template in an unusable status           (L575) -> template_not_ready
* user not found                           (L586) -> not_found
* allocate_storage with no parent storage  (L633) -> template_no_storage_id
* media-info parsing failure re-raised      (L658) -> unable_to_parse_media
* invalid desktop data re-raised            (L733) -> invalid_desktop_data
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


def _ready_template():
    return {
        "id": "tmpl-1",
        "status": "Stopped",
        "description": "template description",
        "icon": "fa-desktop",
        "image": {"id": "img-1", "type": "stock"},
        "os": "linux",
        "hypervisors_pools": ["default"],
        "forced_hyp": False,
        "favourite_hyp": False,
        "parents": [],
        "create_dict": {"hardware": {"disks": [{"storage_id": "st-parent"}]}},
    }


def _user():
    return {"id": "u-1", "username": "bob", "category": "cat-1", "group": "grp-1"}


def _create_dict():
    return {"hardware": {"interfaces": [{"id": "default"}], "memory": 2}}


@pytest.fixture
def stub(monkeypatch):
    """Stub every collaborator new_from_template calls; tests tweak the docs.

    ``docs`` holds the two ``Caches.get_document`` answers ("domains" ->
    template, "users" -> user); a test mutates them to arm a specific guard.
    """
    docs = {"domains": _ready_template(), "users": _user()}

    def get_document(cls, table, item_id, keys=None, invalidate=False):
        return docs[table]

    monkeypatch.setattr(mod.Caches, "get_document", classmethod(get_document))
    monkeypatch.setattr(
        DP,
        "merge_new_data_with_template",
        classmethod(lambda cls, tid, nd: (_create_dict(), {})),
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_interfaces_macs", classmethod(lambda cls, ifaces: ifaces)
    )
    monkeypatch.setattr(
        mod.Helpers, "_parse_media_info", classmethod(lambda cls, cd: cd)
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", classmethod(lambda cls, uid: {})
    )
    monkeypatch.setattr(
        mod.Helpers, "memory_gib_to_kib", staticmethod(lambda mem: 2048)
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        staticmethod(lambda payload, cd: cd),
    )
    return docs


class TestNewFromTemplateGuards:
    def test_template_not_found(self, stub):
        stub["domains"] = None
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "missing-tmpl", "u-1")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_template_unusable_status(self, stub):
        # docstring L575: reject a template that is still being built / failed
        stub["domains"]["status"] = "Failed"
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "tmpl-1", "u-1")
        assert exc.value.error["error"] == "precondition_required"
        assert exc.value.error["description_code"] == "template_not_ready"

    def test_user_not_found(self, stub):
        stub["users"] = None
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "tmpl-1", "missing-user")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_allocate_storage_without_parent_storage_id(self, stub):
        # Template ready, user valid, but disk 0 carries no storage_id: the
        # storage-task create path cannot resolve a parent -> reject.
        stub["domains"]["create_dict"] = {"hardware": {"disks": [{}]}}
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "tmpl-1", "u-1", allocate_storage=True)
        assert exc.value.error["error"] == "precondition_required"
        assert exc.value.error["description_code"] == "template_no_storage_id"

    def test_parse_media_info_failure_reraised(self, stub, monkeypatch):
        # allocate_storage=False skips the storage row; the very next step,
        # _parse_media_info, blows up and must surface as a typed Error.
        monkeypatch.setattr(
            mod.Helpers,
            "_parse_media_info",
            classmethod(lambda cls, cd: (_ for _ in ()).throw(RuntimeError("boom"))),
        )
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "tmpl-1", "u-1", allocate_storage=False)
        assert exc.value.error["error"] == "internal_server"
        assert exc.value.error["description_code"] == "unable_to_parse_media"

    def test_invalid_desktop_data_reraised(self, stub, monkeypatch):
        # Reach the Pydantic validation; make the schema reject the row.
        def _boom(**kwargs):
            raise ValueError("invalid")

        monkeypatch.setattr(mod, "DesktopFromTemplate", _boom)
        with pytest.raises(Error) as exc:
            DP.new_from_template("d", "desc", "tmpl-1", "u-1", allocate_storage=False)
        assert exc.value.error["error"] == "bad_request"
        assert exc.value.error["description_code"] == "invalid_desktop_data"
