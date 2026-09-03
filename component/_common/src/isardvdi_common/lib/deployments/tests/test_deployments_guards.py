#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``DeploymentsProcessed`` in ``lib/deployments/deployments.py``.

* ``check_deployment_bookings`` -- a future booking with fewer units than the
  deployment would need on recreate is refused.
* ``validate_tag_desktop_id_for_deployment`` -- unknown deployment / a
  tag_desktop_id not belonging to it are refused (and the bulk variant loops it).
* ``add_desktops_to_deployment`` -- unknown deployment / template, and a template
  the user may not use, are refused before any desktop is built.

Only rethink and the collaborators are stubbed; the decisions are the code's.
The ``@cached`` validator's cache is cleared in the fixture (rule 4).
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.deployments import deployments as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DeploymentsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DeploymentsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", tuple(x)))
    monkeypatch.setattr(mod.r, "now", lambda: 0)
    # @cached validator: start from an empty cache so a prior result can't mask.
    mod.DeploymentsProcessed.clear_validate_tag_desktop_id_for_deployment_cache()
    return {
        "mod": mod,
        "Cls": mod.DeploymentsProcessed,
        "router": router,
        "mp": monkeypatch,
    }


class TestCheckDeploymentBookings:
    def _wire(self, stub, bookings, n_users):
        stub["router"](
            "bookings"
        ).get_all.return_value.filter.return_value.run.return_value = bookings
        stub["mp"].setattr(
            stub["mod"].DeploymentUsers,
            "get_selected_users",
            classmethod(lambda cls, *a, **k: [{"id": f"u{i}"} for i in range(n_users)]),
        )

    def _deployment(self):
        return {"id": "dep1", "allowed": {}, "create_dict": [{"name": "d"}]}

    def test_booking_with_too_few_units_refused(self, stub):
        self._wire(stub, [{"units": 1, "start": "s", "end": "e"}], n_users=3)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].check_deployment_bookings(
                {"role_id": "admin"}, self._deployment()
            )
        assert (
            exc.value.error["description_code"]
            == "deployment_recreate_booking_not_enough_units"
        )

    def test_booking_with_enough_units_passes(self, stub):
        self._wire(stub, [{"units": 5, "start": "s", "end": "e"}], n_users=3)
        assert (
            stub["Cls"].check_deployment_bookings(
                {"role_id": "admin"}, self._deployment()
            )
            is None
        )


class TestValidateTagDesktopId:
    def _deployment(self, stub, deployment):
        stub["mp"].setattr(
            stub["mod"].Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: deployment),
        )

    def test_unknown_deployment_not_found(self, stub):
        self._deployment(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_tag_desktop_id_for_deployment("gone", "t1")
        assert exc.value.error["error"] == "not_found"

    def test_tag_not_in_deployment_rejected(self, stub):
        self._deployment(stub, {"create_dict": [{"tag_desktop_id": "other"}]})
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].validate_tag_desktop_id_for_deployment("dep1", "ghost")
        assert (
            exc.value.error["description_code"]
            == "invalid_tag_desktop_id_for_deployment"
        )

    def test_valid_tag_passes(self, stub):
        self._deployment(stub, {"create_dict": [{"tag_desktop_id": "t1"}]})
        assert stub["Cls"].validate_tag_desktop_id_for_deployment("dep1", "t1") is None

    def test_bulk_rejects_on_bad_member(self, stub):
        self._deployment(stub, {"create_dict": [{"tag_desktop_id": "t1"}]})
        with pytest.raises(ErrorBase):
            stub["Cls"].validate_tag_desktop_ids_for_deployment("dep1", ["t1", "ghost"])


class TestAddDesktopsToDeployment:
    def _docs(self, stub, mapping):
        stub["mp"].setattr(
            stub["mod"].Caches,
            "get_document",
            classmethod(lambda cls, table, _id, *a, **k: mapping.get((table, _id))),
        )

    # NOTE: the "unknown deployment -> not_found" guard of add_desktops_to_deployment
    # is intentionally NOT unit-tested: with a minimal input the per-template
    # not_found guard right after it ALSO raises not_found, so no single mutation
    # of the deployment guard alone flips the outcome (it would need a valid,
    # allowed template plus the whole downstream build stubbed). The equivalent
    # deployment-not-found guard IS covered on validate_tag_desktop_id_for_deployment.

    def test_unknown_template_not_found(self, stub):
        self._docs(stub, {("deployments", "dep1"): {"id": "dep1"}})  # template -> None
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].add_desktops_to_deployment(
                {}, "dep1", [{"template_id": "tmpl-x"}]
            )
        assert exc.value.error["error"] == "not_found"

    def test_template_not_allowed_forbidden(self, stub):
        self._docs(
            stub,
            {
                ("deployments", "dep1"): {"id": "dep1"},
                ("domains", "tmpl-x"): {
                    "id": "tmpl-x",
                    "description": "d",
                    "image": {},
                },
            },
        )
        stub["mp"].setattr(
            stub["mod"].TemplatesProcessed,
            "check_template_status",
            classmethod(lambda cls, *a, **k: None),
        )
        stub["mp"].setattr(
            stub["mod"].Alloweds,
            "is_allowed",
            classmethod(lambda cls, *a, **k: False),
        )
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].add_desktops_to_deployment(
                {}, "dep1", [{"template_id": "tmpl-x"}]
            )
        assert exc.value.error["description_code"] == "template_not_allowed"
