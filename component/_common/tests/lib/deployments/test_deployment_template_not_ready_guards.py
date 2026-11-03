#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Synchronous "template not ready" guards on the deployment paths.

Before this fix a deployment created (or edited/recreated) with a template in
``CreatingTemplate`` (or any other unusable status) returned a success code and
then silently produced zero desktops: the per-desktop ``new_from_template``
raised ``template_not_ready`` inside the background ``new_from_templateTh`` loop,
which swallowed it. These guards move the check *before* anything is created or
mutated, so the caller gets a synchronous 428.

Each method runs unmocked; rethink and the per-template collaborators are
stubbed. The assertions pin the SPECIFIC ``template_not_ready`` code (not merely
"some Error"): the create loop sits next to a ``not_found`` guard, so a test that
only checked "raises" could not tell the two apart (mutation-method blind spot).
"""
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployment_users as umod
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed
DU = umod.DeploymentUsers


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Dispatched(Exception):
    """Raised by the stubbed dispatch to prove the create path reached it."""


@pytest.fixture
def rdb(monkeypatch):
    """Stub the shared rethink connection on both DeploymentsProcessed and
    DeploymentUsers; return the single mocked ``r.table`` both modules see."""
    for m, cls in ((mod, DP), (umod, DU)):
        monkeypatch.setattr(cls, "_rdb_context", classmethod(lambda cls: _Ctx()))
        monkeypatch.setattr(
            type(cls), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
        )
    tbl = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    monkeypatch.setattr(umod.r, "table", lambda name: tbl)
    monkeypatch.setattr(umod.r, "args", lambda x: ("ARGS", x))
    return tbl


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
@pytest.fixture
def create_env(monkeypatch, rdb):
    state = {"status": "Stopped"}

    def get_document(cls, table, item_id, keys=None, invalidate=False):
        if table == "domains":
            return {
                "id": "t-1",
                "status": state["status"],
                "description": "d",
                "image": {"id": "i"},
            }
        return {"id": item_id}

    monkeypatch.setattr(mod.Caches, "get_document", classmethod(get_document))
    monkeypatch.setattr(
        mod.DeploymentUsers,
        "get_selected_users",
        classmethod(lambda cls, *a, **k: [{"id": "u-1"}]),
    )
    monkeypatch.setattr(
        mod.Quotas, "deployment_create", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(
        mod.Helpers, "check_duplicate", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(
        mod.TemplatesProcessed,
        "check_template_status",
        classmethod(lambda cls, *a, **k: None),
    )
    monkeypatch.setattr(
        mod.Alloweds, "is_allowed", classmethod(lambda cls, *a, **k: True)
    )
    monkeypatch.setattr(
        mod.DesktopViewers,
        "check_new_desktop_viewers",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "strip_nested_virtualization",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "merge_new_data_with_template",
        classmethod(
            lambda cls, tid, nd: ({"hardware": {"memory": 2}, "reservables": None}, {})
        ),
    )
    monkeypatch.setattr(
        mod.Helpers, "_parse_media_info", classmethod(lambda cls, cd: cd)
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        classmethod(lambda cls, payload, cd: {"limited_hardware": []}),
    )
    monkeypatch.setattr(mod.Helpers, "memory_gib_to_kib", staticmethod(lambda m: 2048))
    monkeypatch.setattr(
        mod, "DeploymentModel", lambda **k: MagicMock(model_dump=lambda **kk: {})
    )
    monkeypatch.setattr(
        mod.DeploymentsProcessed,
        "create_deployment_desktops",
        classmethod(lambda cls, *a, **k: (_ for _ in ()).throw(_Dispatched())),
    )
    return state


def _create():
    return DP.create(
        payload={"user_id": "u-1", "role_id": "admin"},
        name="Deployment name",
        description="d",
        selected={
            "users": ["u-1"],
            "groups": False,
            "categories": False,
            "roles": False,
        },
        desktops=[{"template_id": "t-1", "name": "Desktop name"}],
    )


def test_create_with_not_ready_template_raises_before_dispatch(create_env):
    create_env["status"] = "CreatingTemplate"
    with pytest.raises(Error) as exc:
        _create()
    assert exc.value.error["error"] == "precondition_required"
    assert exc.value.error["description_code"] == "template_not_ready"


def test_create_with_ready_template_reaches_dispatch(create_env):
    # Control: a Stopped template passes the guard and reaches the background
    # dispatch (proven by the sentinel) exactly as before.
    create_env["status"] = "Stopped"
    with pytest.raises(_Dispatched):
        _create()


# --------------------------------------------------------------------------- #
# recreate (_prepare_recreate)
# --------------------------------------------------------------------------- #
def _dep_row():
    return {
        "id": "dep-1",
        "name": "dep",
        "tag_visible": False,
        "allowed": {},
        "create_dict": [
            {
                "name": "recipe",
                "template": "t-1",
                "tag_desktop_id": "td-1",
                "hardware": {"memory": 2048, "interfaces": [{"id": "default"}]},
            }
        ],
    }


@pytest.fixture
def recreate_env(monkeypatch, rdb):
    state = {"status": "Stopped"}
    dep = _dep_row()

    def get_document(cls, table, item_id, keys=None, invalidate=False):
        if table == "deployments":
            return dep
        if table == "domains":
            return {"id": "t-1", "status": state["status"]}
        return {"id": item_id}

    monkeypatch.setattr(mod.Caches, "get_document", classmethod(get_document))
    rdb.get.return_value.run.return_value = dep
    monkeypatch.setattr(
        mod.DeploymentsProcessed,
        "_parse_booking",
        classmethod(lambda cls, did: {"next_booking_end": None}),
    )
    monkeypatch.setattr(
        mod.DeploymentUsers,
        "get_selected_users",
        classmethod(lambda cls, *a, **k: [{"id": "u-1"}]),
    )
    return state


def test_prepare_recreate_with_not_ready_template_raises(recreate_env):
    recreate_env["status"] = "CreatingTemplate"
    with pytest.raises(Error) as exc:
        DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
    assert exc.value.error["description_code"] == "template_not_ready"


def test_prepare_recreate_with_ready_template_builds_plan(recreate_env):
    # Control: ready template -> returns (deployment, plan) with one recipe.
    recreate_env["status"] = "Stopped"
    deployment, plan = DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
    assert len(plan) == 1


# --------------------------------------------------------------------------- #
# edit_deployment_users
# --------------------------------------------------------------------------- #
@pytest.fixture
def edit_env(monkeypatch, rdb):
    state = {"status": "Stopped", "booking_checked": False, "recreated": False}
    dep = _dep_row()

    def get_document(cls, table, item_id, keys=None, invalidate=False):
        if table == "deployments":
            return dep
        if table == "domains":
            return {"id": "t-1", "status": state["status"]}
        return {"id": item_id}

    monkeypatch.setattr(umod.Caches, "get_document", classmethod(get_document))
    rdb.get.return_value.run.return_value = dep
    rdb.get.return_value.update.return_value.run.return_value = None
    rdb.get_all.return_value.pluck.return_value.__getitem__.return_value.run.return_value = (
        []
    )

    def _booking(cls, did):
        state["booking_checked"] = True

    monkeypatch.setattr(
        umod.DeploymentUsers, "check_no_scheduled_booking", classmethod(_booking)
    )
    monkeypatch.setattr(
        umod.DeploymentUsers, "get_selected_users", classmethod(lambda cls, *a, **k: [])
    )
    monkeypatch.setattr(
        umod.Caches, "invalidate_cache", classmethod(lambda cls, *a, **k: None)
    )

    def _recreate(cls, payload, did):
        state["recreated"] = True

    monkeypatch.setattr(mod.DeploymentsProcessed, "recreate", classmethod(_recreate))
    return state


def _allowed():
    return {
        "users": ["u-1", "u-2"],
        "groups": False,
        "categories": False,
        "roles": False,
    }


def test_edit_users_not_ready_template_raises_before_mutation(edit_env):
    edit_env["status"] = "CreatingTemplate"
    with pytest.raises(Error) as exc:
        DU.edit_deployment_users({"user_id": "u-1"}, "dep-1", _allowed())
    assert exc.value.error["description_code"] == "template_not_ready"
    # Fired before any side effect: no booking check, no allowed write, no recreate.
    assert edit_env["booking_checked"] is False
    assert edit_env["recreated"] is False


def test_edit_users_ready_template_proceeds(edit_env):
    # Control: ready template -> runs through to recreate without raising.
    edit_env["status"] = "Stopped"
    assert DU.edit_deployment_users({"user_id": "u-1"}, "dep-1", _allowed()) is None
    assert edit_env["recreated"] is True
