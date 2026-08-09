#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DeploymentsProcessed._prepare_recreate``.

Recreate validates the whole plan *before* deleting the live desktops, so a
bad recipe fails fast instead of leaving an empty deployment. Pinned:

* unknown deployment (L858) not_found;
* a recipe whose template is missing (L880) not_found;
* a recipe missing ``hardware.memory`` (L888) bad_request;
* a recipe missing ``hardware.interfaces`` (L893) bad_request.

``_prepare_recreate`` runs unmocked; the document lookups, the rethink read,
the booking parse and the user resolution are stubbed.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(monkeypatch):
    """Happy-path stubs; ``state`` sets the deployment/template/recipe."""
    state = {
        "deployment_doc": {"id": "dep-1"},  # what get_document("deployments") returns
        "template": {"id": "t-1"},  # what get_document("domains") returns
        "deployment": {
            "id": "dep-1",
            "tag_visible": True,
            "allowed": {},
            "create_dict": [],
        },
    }

    def get_document(cls, table, did, keys=None):
        return state["deployment_doc"] if table == "deployments" else state["template"]

    monkeypatch.setattr(mod.Caches, "get_document", classmethod(get_document))
    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = MagicMock(name="r.table")
    tbl.get.return_value.run.return_value = state["deployment"]
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    monkeypatch.setattr(DP, "_parse_booking", classmethod(lambda cls, did: {}))
    monkeypatch.setattr(
        mod.DeploymentUsers,
        "get_selected_users",
        classmethod(lambda cls, *a, **k: ["u-1"]),
    )
    return state


class TestPrepareRecreateGuards:
    def test_deployment_not_found(self, env):
        env["deployment_doc"] = None
        with pytest.raises(Error) as exc:
            DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
        assert exc.value.error["description_code"] == "not_found"

    def test_recipe_template_not_found(self, env):
        env["template"] = None  # get_document("domains", ...) -> missing
        env["deployment"]["create_dict"] = [{"template": "t-x", "name": "r"}]
        with pytest.raises(Error) as exc:
            DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
        assert exc.value.error["description_code"] == "not_found"

    def test_recipe_missing_memory(self, env):
        env["deployment"]["create_dict"] = [
            {"template": "t-1", "name": "r", "hardware": {"interfaces": []}}
        ]
        with pytest.raises(Error) as exc:
            DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
        assert exc.value.error["error"] == "bad_request"

    def test_recipe_missing_interfaces(self, env):
        env["deployment"]["create_dict"] = [
            {"template": "t-1", "name": "r", "hardware": {"memory": 2}}
        ]
        with pytest.raises(Error) as exc:
            DP._prepare_recreate({"user_id": "u-1"}, "dep-1")
        assert exc.value.error["error"] == "bad_request"
