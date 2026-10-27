# SPDX-License-Identifier: AGPL-3.0-or-later

"""A desktop's disk problems: quick fixes run at once, costly ones only when allowed."""

from unittest.mock import MagicMock, patch

import pytest
from api.services import storage_problems as sp
from api.services.error import Error
from api.services.storage_problems import StorageProblemsService
from isardvdi_common.helpers.alloweds import Alloweds

USER = {"user_id": "u1", "role_id": "user", "category_id": "c1", "group_id": "g1"}
ADMIN = {**USER, "user_id": "a1", "role_id": "admin"}
EMPTY = {"roles": False, "categories": False, "groups": False, "users": False}
ROWS = {
    "leaky": {
        "status": "ready",
        "directory_path": "/isard/groups",
        "pending_actions": {"repair_leaks": {"since": 100}, "dig_holes": {}},
        "qemu-img-info": {"actual-size": 1 << 30},
    },
    "busy": {"status": "maintenance", "directory_path": "/isard/groups"},
    "fine": {"status": "ready", "directory_path": "/isard/groups"},
    "damaged": {"status": "damaged", "directory_path": "/isard/groups"},
    "chain": {
        "status": "broken_chain",
        "directory_path": "/isard/groups",
        "pending_actions": {"check_integrity": {}},
    },
    "review": {
        "status": "ready",
        "directory_path": "/isard/groups",
        "pending_actions": {"review_damage": {}},
    },
}


@pytest.fixture
def env():
    storage = MagicMock()
    for method in ("check_integrity", "check_backing_chain", "repair", "dig_holes"):
        getattr(storage, method).return_value = f"task-{method}"
    storage.sparsify.return_value = "task-sparsify"
    allowed = {"value": dict(EMPTY)}
    with (
        patch.object(sp.Helpers, "owns_domain_id", return_value=True),
        patch.object(sp, "Domain") as domain,
        patch.object(sp, "Storage") as storage_cls,
        patch.object(sp.StoragePool, "get_best_for_action") as pool,
        patch.object(sp.queue_estimate, "estimate_new") as estimate,
        patch.object(
            sp,
            "_running_task",
            side_effect=lambda i: {"id": "t9", "position": 3} if i == "busy" else None,
        ),
        patch.object(
            Alloweds,
            "get_storage_repair_allowed_dict",
            side_effect=lambda: allowed["value"],
        ),
        patch.object(Alloweds, "check_secondary_groups", return_value=True),
    ):
        domain.return_value.kind = "desktop"
        domain.return_value.create_dict = {
            "hardware": {"disks": [{"storage_id": i} for i in [*ROWS, "gone"]]}
        }
        storage_cls.get.side_effect = lambda i: ROWS.get(i)
        storage_cls.return_value = storage
        pool.return_value.id = "p1"
        estimate.return_value = {"tier": "standard", "run_seconds": 5}
        yield {"storage": storage, "cls": storage_cls, "allowed": allowed}


def _by_disk(report):
    return {d["storage_id"]: d for d in report["disks"]}


def _problems(disk):
    return [(p["code"], p["fix"], p["mode"], p["allowed"]) for p in disk["problems"]]


def test_each_disk_says_how_its_problems_are_handled(env):
    report = StorageProblemsService.report(USER, "d1")
    disks = _by_disk(report)
    assert report["can_repair_costly"] is False
    assert _problems(disks["leaky"]) == [
        ("storage_leaks", "repair_leaks", "quick", True),
        ("storage_zeros", "dig_holes", "costly", False),
    ]
    assert disks["leaky"]["problems"][0]["pending_since"] == 100
    assert disks["busy"]["problems"][0]["mode"] == "wait"
    assert disks["busy"]["task"]["position"] == 3
    assert disks["fine"]["problems"] == []
    assert disks["review"]["problems"][0]["mode"] == "admin"
    assert disks["gone"]["problems"][0]["code"] == "storage_missing"


def test_an_admin_sees_the_costly_fixes_as_allowed(env):
    disks = _by_disk(StorageProblemsService.report(ADMIN, "d1"))
    assert ("storage_zeros", "dig_holes", "costly", True) in _problems(disks["leaky"])


def test_handling_queues_one_quick_fix_per_disk_and_records_the_rest(env):
    report = StorageProblemsService.handle(USER, "d1")
    runs = {(r["storage_id"], r["fix"]): r for r in report["quick_fixes"]}
    assert runs[("leaky", "repair_leaks")]["task_id"] == "task-repair"
    assert runs[("damaged", "check")]["task_id"] == "task-check_integrity"
    assert runs[("chain", "check_backing_chain")]["task_id"] == (
        "task-check_backing_chain"
    )
    assert runs[("chain", "check")] == {
        "storage_id": "chain",
        "fix": "check",
        "recorded": "check_integrity",
    }
    assert ("busy", "check") not in runs and ("fine", "check") not in runs
    env["cls"].flag_pending.assert_called_once_with(
        "chain",
        "check_integrity",
        found_by="a user action on the desktop",
        if_absent=True,
    )
    storage = env["storage"]
    storage.dig_holes.assert_not_called()
    storage.sparsify.assert_not_called()
    assert all(c.args[1] == "leaks" for c in storage.repair.call_args_list)


def test_a_refused_quick_fix_is_recorded_for_the_sweep(env):
    env["storage"].repair.side_effect = Error(
        "precondition_required", "open", description_code="storage_open_not_checkable"
    )
    runs = StorageProblemsService.handle(USER, "d1")["quick_fixes"]
    leak = next(r for r in runs if r["storage_id"] == "leaky")
    assert leak["refused"] == "storage_open_not_checkable"
    assert leak["recorded"] == "repair_leaks"
    env["cls"].flag_pending.assert_any_call(
        "leaky",
        "repair_leaks",
        found_by="a user action on the desktop",
        if_absent=True,
    )


def test_a_failing_handle_never_masks_the_start_error(env):
    with patch.object(StorageProblemsService, "handle", side_effect=RuntimeError):
        assert StorageProblemsService.handle_quietly(USER, "d1") is None


@pytest.mark.parametrize("fix", ["repair_all", "dig_holes"])
def test_a_user_the_list_does_not_match_gets_forbidden_for_a_costly_fix(env, fix):
    storage_id = "damaged" if fix == "repair_all" else "leaky"
    with pytest.raises(Error) as raised:
        StorageProblemsService.fix(USER, "d1", storage_id, fix)
    assert raised.value.status_code == 403
    assert raised.value.error["description_code"] == "storage_repair_not_allowed"
    env["storage"].repair.assert_not_called()
    env["storage"].dig_holes.assert_not_called()


@pytest.mark.parametrize(
    "key, value",
    [
        ("roles", ["user"]),
        ("categories", ["c1"]),
        ("groups", ["g1"]),
        ("users", ["u1"]),
    ],
)
def test_a_user_the_list_matches_runs_a_costly_fix(env, key, value):
    env["allowed"]["value"] = {**EMPTY, key: value}
    out = StorageProblemsService.fix(USER, "d1", "leaky", "dig_holes")
    assert out["task_id"] == "task-dig_holes"


def test_an_admin_always_runs_a_costly_fix(env):
    out = StorageProblemsService.fix(ADMIN, "d1", "damaged", "repair_all")
    assert out["task_id"] == "task-repair"
    assert env["storage"].repair.call_args.args == ("a1", "all")
    assert env["storage"].repair.call_args.kwargs["priority"] == "maintenance"


def test_a_quick_fix_needs_no_permission(env):
    out = StorageProblemsService.fix(USER, "d1", "leaky", "repair_leaks")
    assert out["task_id"] == "task-repair"
    assert env["storage"].repair.call_args.args == ("u1", "leaks")


@pytest.mark.parametrize(
    "storage_id, fix",
    [("fine", "check"), ("review", "check"), ("leaky", "sparsify")],
)
def test_a_fix_the_disk_does_not_call_for_is_refused(env, storage_id, fix):
    env["allowed"]["value"] = {**EMPTY, "users": ["u1"]}
    with pytest.raises(Error) as raised:
        StorageProblemsService.fix(USER, "d1", storage_id, fix)
    assert raised.value.error["description_code"] == "storage_fix_not_needed"


def test_a_disk_with_a_task_in_progress_is_refused(env):
    ROWS["busy"]["pending_actions"] = {"repair_leaks": {}}
    try:
        with pytest.raises(Error) as raised:
            StorageProblemsService.fix(USER, "d1", "busy", "repair_leaks")
    finally:
        ROWS["busy"].pop("pending_actions")
    assert raised.value.error["description_code"] == "storage_fix_in_progress"


def test_a_disk_of_another_desktop_is_not_found(env):
    with pytest.raises(Error) as raised:
        StorageProblemsService.fix(ADMIN, "d1", "elsewhere", "check")
    assert raised.value.status_code == 404


def test_a_shared_template_is_neither_reported_nor_handled_nor_fixed(env):
    with patch.object(sp, "Domain") as domain:
        domain.return_value.kind = "template"
        for call in (
            lambda: StorageProblemsService.report(USER, "t1"),
            lambda: StorageProblemsService.handle(USER, "t1"),
            lambda: StorageProblemsService.fix(USER, "t1", "leaky", "repair_leaks"),
        ):
            with pytest.raises(Error) as raised:
                call()
            assert raised.value.status_code == 403
