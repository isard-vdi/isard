# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``Quotas`` in ``helpers/quotas.py``.

* ``deployment_desktop_start`` -- a desktop with no deployment tag is refused
  (``precondition_required``); an admin bypasses the quota gate; a regular user
  is put through ``check_field_quotas``.
* ``user_hardware_allowed`` -- an unknown hardware ``kind`` is refused
  (``bad_request``), a missing ``domain_id`` is ``not_found``, and a valid kind
  builds only that section.

The real function decides; only ``Caches`` / ``Alloweds`` / the rethink layer
and the sibling quota helpers are stubbed. Errors are asserted by type +
``description_code``; the admin-bypass test also asserts the quota gate is NOT
invoked.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


def _clear_cachetools_caches(*modules):
    """Empty every ``cachetools`` cache reachable from these modules.

    Several of these helpers are ``@cached``, so a result another test left
    behind is returned without the guard ever running. The test then passes for
    the wrong reason, and whether it passes at all depends on ordering.
    """
    seen = set()
    for module in modules:
        for owner in vars(module).values():
            if not isinstance(owner, type):
                continue
            for attr in vars(owner).values():
                fn = getattr(attr, "__func__", attr)
                cache = getattr(fn, "cache", None)
                if cache is not None and id(cache) not in seen:
                    seen.add(id(cache))
                    try:
                        cache.clear()
                    except Exception:
                        pass


@pytest.fixture
def q(monkeypatch):
    from isardvdi_common.helpers import caches as caches_mod
    from isardvdi_common.helpers import quotas as mod

    _clear_cachetools_caches(mod, caches_mod)

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Quotas, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Quotas),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    return {"mod": mod, "Cls": mod.Quotas, "mp": monkeypatch}


class TestDeploymentDesktopStart:
    def test_desktop_without_deployment_tag_refused(self, q):
        q["mp"].setattr(
            q["mod"].Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: {"tag": "", "id": "d1"}),
        )
        q["mp"].setattr(
            q["mod"].Caches,
            "get_cached_user_with_names",
            classmethod(lambda cls, uid: {"role": "admin", "id": uid, "name": "n"}),
        )
        with pytest.raises(ErrorBase) as exc:
            q["Cls"].deployment_desktop_start("u-tag", "d-tag")
        assert exc.value.error["error"] == "precondition_required"
        assert exc.value.status_code == 428

    def test_admin_bypasses_quota_gate(self, q):
        desktop = {"tag": "dep-1", "id": "d1"}
        q["mp"].setattr(
            q["mod"].Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: desktop),
        )
        q["mp"].setattr(
            q["mod"].Caches,
            "get_cached_user_with_names",
            classmethod(lambda cls, uid: {"role": "admin", "id": uid, "name": "n"}),
        )
        gate = MagicMock(name="check_field_quotas")
        q["mp"].setattr(
            q["Cls"], "check_field_quotas", classmethod(lambda cls, *a, **k: gate(*a))
        )

        result = q["Cls"].deployment_desktop_start("u-admin", "d-admin")

        assert result is desktop
        # Admin must never be put through the quota gate.
        gate.assert_not_called()

    def test_regular_user_goes_through_quota_gate(self, q):
        desktop = {"tag": "dep-1", "id": "d1"}
        q["mp"].setattr(
            q["mod"].Caches,
            "get_document",
            classmethod(lambda cls, *a, **k: desktop),
        )
        q["mp"].setattr(
            q["mod"].Caches,
            "get_cached_user_with_names",
            classmethod(
                lambda cls, uid: {"role": "user", "id": uid, "name": "n", "group": "g1"}
            ),
        )

        def _raise(cls, user, field, amount, err):
            raise ErrorBase(
                "precondition_required",
                err["error_description"],
                description_code=err["error_description_code"],
            )

        q["mp"].setattr(q["Cls"], "check_field_quotas", classmethod(_raise))

        with pytest.raises(ErrorBase) as exc:
            q["Cls"].deployment_desktop_start("u-reg", "d-reg")
        # A non-admin is enforced against the started-deployment-desktops quota.
        assert (
            exc.value.error["description_code"]
            == "deployment_start_user_quota_exceeded"
        )


class TestUserHardwareAllowed:
    def test_unknown_kind_refused(self, q):
        with pytest.raises(ErrorBase) as exc:
            q["Cls"].user_hardware_allowed(
                {"role_id": "user", "user_id": "u-hw"}, kind="bogus"
            )
        assert exc.value.error["error"] == "bad_request"
        assert exc.value.status_code == 400

    def test_missing_domain_is_not_found(self, q):
        # r.table("domains").get(domain_id)["create_dict"].run() -> None
        table = MagicMock(name="table-domains")
        table.get.return_value.__getitem__.return_value.run.return_value = None
        q["mp"].setattr(q["mod"].r, "table", MagicMock(return_value=table))
        with pytest.raises(ErrorBase) as exc:
            q["Cls"].user_hardware_allowed(
                {"role_id": "user", "user_id": "u-hw"},
                kind="graphics",
                domain_id="nope",
            )
        assert exc.value.error["error"] == "not_found"
        assert exc.value.error["description_code"] == "not_found"

    def test_valid_kind_builds_only_that_section(self, q):
        q["mp"].setattr(
            q["mod"].Alloweds,
            "get_items_allowed",
            classmethod(lambda cls, *a, **k: ["G1"]),
        )
        out = q["Cls"].user_hardware_allowed(
            {"role_id": "user", "user_id": "u-hw"}, kind="graphics"
        )
        # Only the requested kind is present.
        assert out == {"graphics": ["G1"]}
