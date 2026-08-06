#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-recipe guards on ``DeploymentsProcessed.add_desktops_to_deployment``.

Adding desktops to an existing deployment re-runs the same recipe wall as
create: for each new recipe it rejects an unknown template (not_found), a
template the user may not use (template_not_allowed), media that fails to
parse (unable_to_parse_media) and quota-limited hardware, then rejects a set
whose desktops do not share the same vGPU profiles
(deployment_reservables_not_equal).

``add_desktops_to_deployment`` runs unmocked; the document lookups, the
per-template collaborators and the schema are stubbed.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


@pytest.fixture
def env(monkeypatch):
    state = {"template": {"id": "t-1", "description": "d", "image": {"id": "i"}}}

    def get_document(cls, table, did, keys=None):
        return {"id": "dep-1"} if table == "deployments" else state["template"]

    monkeypatch.setattr(mod.Caches, "get_document", classmethod(get_document))
    monkeypatch.setattr(
        mod.TemplatesProcessed,
        "check_template_status",
        classmethod(lambda cls, status, template: None),
    )
    monkeypatch.setattr(
        mod.Alloweds, "is_allowed", classmethod(lambda cls, payload, item, table: True)
    )
    monkeypatch.setattr(
        mod.DesktopViewers,
        "check_new_desktop_viewers",
        classmethod(lambda cls, desktop, template: None),
    )
    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "merge_new_data_with_template",
        classmethod(
            lambda cls, tid, desktop: (
                {"hardware": {}, "reservables": {"vgpus": desktop.get("vgpus")}},
                {},
            )
        ),
    )
    monkeypatch.setattr(
        mod.Helpers, "_parse_media_info", classmethod(lambda cls, cd: cd)
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        staticmethod(lambda payload, cd: {**cd, "limited_hardware": []}),
    )
    return state


def _add(desktops):
    return DP.add_desktops_to_deployment({"user_id": "u-1"}, "dep-1", desktops)


class TestAddDesktopsGuards:
    def test_template_not_found(self, env):
        env["template"] = None
        with pytest.raises(Error) as exc:
            _add([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "not_found"

    def test_template_not_allowed(self, env, monkeypatch):
        monkeypatch.setattr(
            mod.Alloweds, "is_allowed", classmethod(lambda cls, *a: False)
        )
        with pytest.raises(Error) as exc:
            _add([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "template_not_allowed"

    def test_unable_to_parse_media(self, env, monkeypatch):
        def _boom(cls, cd):
            raise RuntimeError("bad media")

        monkeypatch.setattr(mod.Helpers, "_parse_media_info", classmethod(_boom))
        with pytest.raises(Error) as exc:
            _add([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "unable_to_parse_media"

    def test_limited_hardware_rejected(self, env, monkeypatch):
        monkeypatch.setattr(
            mod.Quotas,
            "limit_user_hardware_allowed",
            staticmethod(lambda payload, cd: {**cd, "limited_hardware": ["vcpus"]}),
        )
        with pytest.raises(Error) as exc:
            _add([{"template_id": "t-1"}])
        assert exc.value.error["error"] == "bad_request"

    def test_reservables_not_equal(self, env):
        with pytest.raises(Error) as exc:
            _add(
                [
                    {"template_id": "t-1", "vgpus": ["a"]},
                    {"template_id": "t-1", "vgpus": ["b"]},
                ]
            )
        assert exc.value.error["description_code"] == "deployment_reservables_not_equal"
