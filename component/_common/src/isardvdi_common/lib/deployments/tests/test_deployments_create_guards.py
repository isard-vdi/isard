#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DeploymentsProcessed.create`` — the per-recipe wall.

For every desktop recipe in a new deployment the create path rejects:

* an unknown template (L1005) not_found;
* a template the user is not allowed to use (L1014) template_not_allowed;
* media info that fails to parse (L1036) unable_to_parse_media;
* hardware limited by the user's quota (L1045) bad_request;

and, once every recipe is parsed, a deployment whose desktops do not all
share the same vGPU set (L1073) deployment_reservables_not_equal.

``create`` runs unmocked; the user resolution, quota/duplicate checks and
the per-template collaborators are stubbed, so each reject decision is the
real code.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


@pytest.fixture
def env(monkeypatch):
    """Stub the create collaborators on a happy path; tests break one."""
    state = {"template": {"id": "t-1", "description": "d", "image": {"id": "i"}}}
    monkeypatch.setattr(
        mod.DeploymentUsers,
        "get_selected_users",
        classmethod(lambda cls, *a, **k: ["u-1"]),
    )
    monkeypatch.setattr(
        mod.Quotas, "deployment_create", classmethod(lambda cls, **k: None)
    )
    monkeypatch.setattr(
        mod.Helpers, "check_duplicate", classmethod(lambda cls, *a, **k: None)
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, table, did, keys=None: state["template"]),
    )
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


def _create(desktops):
    return DP.create(
        {"user_id": "u-1"},
        "dep-name",
        "desc",
        {},
        desktops,
        create_owner_desktop=False,
    )


class TestCreateGuards:
    def test_template_not_found(self, env, monkeypatch):
        monkeypatch.setattr(
            mod.Caches, "get_document", classmethod(lambda cls, *a, **k: None)
        )
        with pytest.raises(Error) as exc:
            _create([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "not_found"

    def test_template_not_allowed(self, env, monkeypatch):
        monkeypatch.setattr(
            mod.Alloweds, "is_allowed", classmethod(lambda cls, *a: False)
        )
        with pytest.raises(Error) as exc:
            _create([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "template_not_allowed"

    def test_unable_to_parse_media(self, env, monkeypatch):
        def _boom(cls, cd):
            raise RuntimeError("bad media")

        monkeypatch.setattr(mod.Helpers, "_parse_media_info", classmethod(_boom))
        with pytest.raises(Error) as exc:
            _create([{"template_id": "t-1"}])
        assert exc.value.error["description_code"] == "unable_to_parse_media"

    def test_limited_hardware_rejected(self, env, monkeypatch):
        monkeypatch.setattr(
            mod.Quotas,
            "limit_user_hardware_allowed",
            staticmethod(lambda payload, cd: {**cd, "limited_hardware": ["vcpus"]}),
        )
        with pytest.raises(Error) as exc:
            _create([{"template_id": "t-1"}])
        assert exc.value.error["error"] == "bad_request"

    def test_reservables_not_equal_across_desktops(self, env):
        with pytest.raises(Error) as exc:
            _create(
                [
                    {"template_id": "t-1", "vgpus": ["a"]},
                    {"template_id": "t-1", "vgpus": ["b"]},
                ]
            )
        assert exc.value.error["description_code"] == "deployment_reservables_not_equal"
