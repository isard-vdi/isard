#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``TemplatesProcessed.check_children`` deployment
propagation and deduplication (regression from cea1f0ff1c).

The template delete confirmation modal renders the tree this method builds.
A deployment hanging off a DERIVED template (or one duplicated deep in the
tree) must appear exactly once, and masked (unowned) deployments must still
be accounted for so ``pending`` and the modal's per-type counts stay honest.

``check_children`` is pure tree logic: it only calls ``Helpers.owns_*``, so
these tests feed dict trees and patch the ownership probes — no RethinkDB.
"""

import pytest


@pytest.fixture
def check_children(monkeypatch):
    """Return ``TemplatesProcessed.check_children`` with ownership probes
    stubbed so, by default, everything is owned. Individual tests override
    ``owns_deployment_id`` to simulate an unowned (masked) node.
    """
    from isardvdi_common.lib.domains.templates import templates as mod

    monkeypatch.setattr(
        mod.Helpers,
        "owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    monkeypatch.setattr(
        mod.Helpers,
        "owns_deployment_id",
        staticmethod(lambda payload, deployment_id, check_co_owner=True: deployment_id),
    )
    return mod.TemplatesProcessed.check_children


def _branch(node_id, kind, children):
    return {
        "id": node_id,
        "kind": kind,
        "title": node_id,
        "user": "u1",
        "children": children,
    }


def _leaf(node_id, kind):
    return {"id": node_id, "kind": kind, "title": node_id, "user": "u1"}


def _raise_unowned(payload, deployment_id, check_co_owner=True):
    raise Exception("not owned")


PAYLOAD = {"user_id": "u1"}


class TestCheckChildrenDeployments:
    def test_deep_deployment_is_returned(self, check_children):
        """A deployment nested under a DERIVED template must survive the
        recursion — this is the exact loss seen in the field."""
        tree = _branch(
            "root",
            "template",
            [_branch("deriv", "template", [_leaf("dep1", "deployment")])],
        )
        result = check_children(PAYLOAD, tree)
        ids = [d.get("id") for d in result["deployments"]]
        assert "dep1" in ids

    def test_duplicated_deployment_appears_once(self, check_children):
        """Same deployment reachable under the root and under a duplicated
        template subtree must be emitted once, not twice."""
        tree = _branch(
            "root",
            "template",
            [
                _leaf("dep1", "deployment"),
                _branch("dup", "template", [_leaf("dep1", "deployment")]),
            ],
        )
        result = check_children(PAYLOAD, tree)
        ids = [d.get("id") for d in result["deployments"]]
        assert ids.count("dep1") == 1
        assert len(result["deployments"]) == 1

    def test_deep_unowned_deployment_sets_pending(self, check_children, monkeypatch):
        """A deep deployment the caller does not own must mask to ``{}`` and
        set ``pending`` — both must survive the recursion too."""
        from isardvdi_common.lib.domains.templates import templates as mod

        monkeypatch.setattr(
            mod.Helpers, "owns_deployment_id", staticmethod(_raise_unowned)
        )
        tree = _branch(
            "root",
            "template",
            [_branch("deriv", "template", [_leaf("dep1", "deployment")])],
        )
        result = check_children(PAYLOAD, tree)
        assert result["pending"] is True
        masked = [d for d in result["deployments"] if d == {}]
        assert len(masked) == 1

    def test_domains_not_regressed(self, check_children):
        """The domains list keeps the root first and every domain node."""
        tree = _branch(
            "root",
            "template",
            [
                _branch(
                    "deriv",
                    "template",
                    [_leaf("desk1", "desktop"), _leaf("dep1", "deployment")],
                )
            ],
        )
        result = check_children(PAYLOAD, tree)
        assert result["domains"][0]["id"] == "root"
        domain_ids = {d.get("id") for d in result["domains"]}
        assert {"root", "deriv", "desk1"} <= domain_ids

    def test_deployment_ids_contains_masked(self, check_children, monkeypatch):
        """``deployment_ids`` is the internal dedup index A2 needs; it must
        include masked (``{}``) deployments, which carry no ``id``."""
        from isardvdi_common.lib.domains.templates import templates as mod

        monkeypatch.setattr(
            mod.Helpers, "owns_deployment_id", staticmethod(_raise_unowned)
        )
        tree = _branch("root", "template", [_leaf("dep1", "deployment")])
        result = check_children(PAYLOAD, tree)
        assert "dep1" in result["deployment_ids"]
