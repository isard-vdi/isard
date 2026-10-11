# SPDX-License-Identifier: AGPL-3.0-or-later
"""The unused-deployment sweeps with a deployment creator that no longer exists."""

import contextlib
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.deployments import deployments as mod
from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed


class _Query:
    """Any ReQL chain; each ``run`` answers the next queued result."""

    def __init__(self, results):
        self.results = results

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __getitem__(self, key):
        return self

    def __lt__(self, other):
        return self

    def __eq__(self, other):
        return self

    def __and__(self, other):
        return self

    __hash__ = object.__hash__

    def run(self, connection):
        return self.results.pop(0)


LIVE = {
    "id": "alive",
    "provider": "local",
    "name": "A",
    "uid": "a",
    "username": "a",
    "role": "user",
    "category": "default",
    "group": "g",
}


@pytest.fixture
def sweep(monkeypatch):
    log = MagicMock(name="log")
    monkeypatch.setattr(mod, "log", log)
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        lambda table, doc_id, *a, **k: LIVE if doc_id == "alive" else None,
    )
    monkeypatch.setattr(
        mod, "get_unused_item_timeout", lambda payload, op: {"cutoff_time": 1}
    )
    monkeypatch.setattr(
        DeploymentsProcessed,
        "_rdb_context",
        classmethod(lambda cls: contextlib.nullcontext()),
    )
    monkeypatch.setattr(
        type(DeploymentsProcessed), "_rdb_connection", property(lambda cls: None)
    )

    def _run(method, results):
        monkeypatch.setattr(mod, "r", _Query(results))
        return getattr(DeploymentsProcessed, method)(), log

    return _run


def test_unused_deployments_takes_all_of_a_deleted_creator_without_an_error(sweep):
    alive_old = [{"id": "d-alive", "user": "alive"}]
    gone_all = [{"id": "d-gone-1", "user": "gone"}, {"id": "d-gone-2", "user": "gone"}]

    result, log = sweep(
        "get_unused_deployments", [["alive", "gone"], alive_old, gone_all]
    )

    assert result == alive_old + gone_all
    log.error.assert_not_called()
    log.exception.assert_not_called()
    log.warning.assert_called_once()
    assert log.warning.call_args.args[1] == 1


def test_unused_deployment_desktops_skips_a_deleted_creator_without_an_error(sweep):
    cold = [{"id": "x", "user": "u", "name": "n", "accessed": 0, "tag": "d-alive"}]

    result, log = sweep(
        "get_unused_deployment_desktops", [["alive", "gone"], ["d-alive"], cold]
    )

    assert [entry["creator"] for entry in result] == ["alive"]
    log.error.assert_not_called()
    log.exception.assert_not_called()


def test_a_live_creator_whose_rule_fails_is_not_swept_whole(sweep, monkeypatch):
    def _broken_rule(payload, op):
        raise TypeError("rule lookup failed")

    monkeypatch.setattr(mod, "get_unused_item_timeout", _broken_rule)
    every_deployment = [{"id": "d-alive", "user": "alive"}]

    result, log = sweep("get_unused_deployments", [["alive"], every_deployment])

    assert result == []
    log.exception.assert_called_once()
