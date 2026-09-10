#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``RecycleBinTemplate.add`` must validate everything that can abort BEFORE
it mutates anything.

Recycling a deployment removes its rows from ``deployments`` and ``domains``
and RethinkDB has no rollback, so if the template turns out not to exist
(delete race) or to have a derivative in another category (``get_template_
with_all_derivatives`` raises ``forbidden`` on the manager path), the
deployments must NOT already have been recycled. This is the ordering bug
that recycled the derived deployments before the abort could fire.

``add`` is exercised in isolation: the instance is built without ``__init__``
(which would hit the DB) and its collaborators are stubbed.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def rb_add(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # Stub the context manager so no real pool connection is acquired.
    # ``self._rdb_connection`` then resolves to None (thread-local empty,
    # override None) and is only handed to the mocked ``.run()`` below, so
    # its value is irrelevant — no need to patch the metaclass property
    # (which has no deleter and breaks monkeypatch teardown).
    monkeypatch.setattr(mod.RecycleBinTemplate, "_rdb_context", lambda self: _Ctx())
    # _add_item_name writes to the recycle_bin entry; stub it so the test
    # observes only the ordering, never a real mutation.
    monkeypatch.setattr(
        mod.RecycleBinTemplate, "_add_item_name", lambda self, name: None
    )

    recycled = []

    class _FakeDeployment:
        def __init__(self, id=None, user_id=None):
            pass

        def add(self, deployment_id):
            recycled.append(deployment_id)

    monkeypatch.setattr(mod, "RecycleBinDeployment", _FakeDeployment)
    monkeypatch.setattr(
        mod.CommonHelpers,
        "get_template_derivated_deployments",
        staticmethod(lambda template_id: [{"id": "dep-1"}, {"id": "dep-2"}]),
    )

    def _make(template_row):
        """domains.get(template_id).run() -> ``template_row`` (dict or None)."""
        table = MagicMock(name="table-domains")
        table.get.return_value.run.return_value = template_row
        monkeypatch.setattr(mod.r, "table", lambda name: table)
        rb = object.__new__(mod.RecycleBinTemplate)
        rb.id = "rb-1"
        rb.agent_id = "admin"
        return rb

    return mod, recycled, _make


class TestRecycleBinTemplateAddValidatesBeforeMutating:
    def test_forbidden_derivative_does_not_recycle_any_deployment(
        self, rb_add, monkeypatch
    ):
        mod, recycled, _make = rb_add

        def _forbidden(template_id, user_id=None):
            raise mod.Error("forbidden", "derivative in another category")

        monkeypatch.setattr(
            mod.CommonHelpers,
            "get_template_with_all_derivatives",
            staticmethod(_forbidden),
        )

        rb = _make({"name": "T", "user": "admin"})
        with pytest.raises(mod.Error) as exc:
            rb.add("tpl-1")

        assert recycled == []  # nothing recycled before the forbidden abort
        assert exc.value.status_code == 403

    def test_missing_template_does_not_recycle_any_deployment(
        self, rb_add, monkeypatch
    ):
        mod, recycled, _make = rb_add

        rb = _make(None)  # domains.get(...).run() -> None → not_found
        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-tpl")

        assert recycled == []
        assert exc.value.status_code == 404
