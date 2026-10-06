# SPDX-License-Identifier: AGPL-3.0-or-later

"""Duplicating a template does not launder a broken one into a healthy-looking copy."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.templates import templates as mod

TP = mod.TemplatesProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(monkeypatch):
    state = {
        "template": {
            "kind": "template",
            "status": "Stopped",
            "create_dict": {"hardware": {"disks": [{"storage_id": "disk-1"}]}},
        },
        "storage": {"disk-1": "ready"},
        "inserted": [],
    }
    tbl = MagicMock(name="r.table(domains)")
    tbl.get.return_value.without.return_value.run.side_effect = lambda conn: state[
        "template"
    ]

    def _insert(doc):
        state["inserted"].append(doc)
        m = MagicMock()
        m.__getitem__.return_value.__getitem__.return_value.run.return_value = "copy-1"
        return m

    tbl.insert.side_effect = _insert
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    monkeypatch.setattr(TP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(TP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(
        mod.Helpers, "get_user_data", classmethod(lambda cls, uid: {"user": uid})
    )

    class FakeStorage:
        @classmethod
        def exists(cls, sid):
            return sid in state["storage"]

        def __init__(self, sid):
            self.status = state["storage"][sid]

    monkeypatch.setattr(mod, "Storage", FakeStorage)
    return state


def _dup():
    return TP.duplicate_template({"user_id": "u1"}, "tpl-1", "copy of tpl-1")


def test_a_healthy_template_duplicates(env):
    assert _dup() == "copy-1"
    assert env["inserted"][0]["status"] == "Stopped"


def test_a_failed_template_is_refused_before_anything_is_written(env):
    """The copy was inserted as Stopped whatever the source said, so a Failed
    template became a healthy-looking one that derived orphan desktops."""
    env["template"]["status"] = "Failed"
    with pytest.raises(Error) as exc:
        _dup()
    assert exc.value.error["description_code"] == "template_failed"
    assert env["inserted"] == []


@pytest.mark.parametrize("status", ["deleted", "maintenance", "non_existing"])
def test_a_template_whose_disk_is_not_ready_is_refused(env, status):
    env["storage"]["disk-1"] = status
    with pytest.raises(Error) as exc:
        _dup()
    assert exc.value.error["description_code"] == "template_storage_not_ready"
    assert env["inserted"] == []


def test_a_template_whose_disk_row_is_gone_is_refused(env):
    env["storage"] = {}
    with pytest.raises(Error) as exc:
        _dup()
    assert exc.value.error["description_code"] == "template_storage_not_ready"


def test_a_template_without_disks_still_duplicates(env):
    env["template"]["create_dict"] = {"hardware": {"disks": []}}
    assert _dup() == "copy-1"
