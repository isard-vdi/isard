"""fake_storage path-handling regression tests (no docker needed)."""

from __future__ import annotations

from anonymize_db import fake_storage


def _capture(monkeypatch):
    calls = []

    def fake_run(container, *args, check=True):
        calls.append(list(args))

        class R:
            returncode = 0
            stderr = ""

        return R()

    monkeypatch.setattr(fake_storage, "_docker_run", fake_run)
    monkeypatch.setattr(fake_storage, "_exists", lambda c, p: False)
    return calls


def test_mkdir_uses_target_parent_for_legacy_slash_ids(monkeypatch):
    # legacy storage id contains '/', so the qcow2 nests below directory_path
    calls = _capture(monkeypatch)
    rows = [
        {
            "id": "default/cat/grp/user/Tmpl",
            "type": "qcow2",
            "directory_path": "/isard/templates",
            "parent": "",
        }
    ]
    ordered = fake_storage.topo_sort_storages(rows)
    fake_storage.materialise_storage(ordered, "isard-storage", force=False)
    mkdirs = [a for a in calls if a[:2] == ["mkdir", "-p"]]
    creates = [a for a in calls if a[:1] == ["qemu-img"]]
    # must mkdir the target's parent (deep), NOT directory_path
    assert mkdirs == [["mkdir", "-p", "/isard/templates/default/cat/grp/user"]]
    assert creates[0][-2] == "/isard/templates/default/cat/grp/user/Tmpl.qcow2"


def test_mkdir_normal_uuid_id_unchanged(monkeypatch):
    calls = _capture(monkeypatch)
    rows = [
        {
            "id": "abcd-1234",
            "type": "qcow2",
            "directory_path": "/isard/groups/g1",
            "parent": "",
        }
    ]
    fake_storage.materialise_storage(
        fake_storage.topo_sort_storages(rows), "isard-storage", force=False
    )
    mkdirs = [a for a in calls if a[:2] == ["mkdir", "-p"]]
    assert mkdirs == [["mkdir", "-p", "/isard/groups/g1"]]  # == directory_path here
