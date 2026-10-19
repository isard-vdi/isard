# SPDX-License-Identifier: AGPL-3.0-or-later

"""One registry decides every disk action, and says why it refuses one."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.storage import actions
from isardvdi_common.lib.storage import storage as lib

DESKTOP = ("desktop", "Stopped")


def _dig(**facts):
    facts.setdefault("status", "ready")
    facts.setdefault("domains", [DESKTOP])
    facts.setdefault("perms", ["r", "w"])
    has_children = facts.pop("has_children", False)
    refused = actions.refusal(
        "dig_holes", has_children=lambda: has_children, storage_id="s1", **facts
    )
    return refused and refused[0]


class TestDigHolesOnlyDigsAStoppedDesktopsLeafDisk:
    def test_a_stopped_desktops_leaf_disk_is_admitted(self):
        assert _dig() is None

    def test_a_failed_desktop_still_blocks_it(self):
        assert _dig(domains=[("desktop", "Failed")]) == "desktops_not_stopped"

    @pytest.mark.parametrize(
        "facts, code",
        [
            ({"status": "maintenance"}, "storage_not_ready"),
            ({"perms": ["r"]}, "storage_read_only"),
            ({"domains": []}, "storage_not_used_by_any_domain"),
            (
                {"domains": [DESKTOP, ("template", "Stopped")]},
                "storage_used_by_template",
            ),
            ({"domains": [("desktop", "Started")]}, "storage_open_by_running_desktop"),
            ({"domains": [("desktop", "Paused")]}, "storage_open_by_running_desktop"),
            ({"has_children": True}, "storage_has_children"),
        ],
        ids=[
            "not-ready",
            "read-only",
            "no-domain",
            "template",
            "running",
            "paused",
            "children",
        ],
    )
    def test_each_refusal_says_why(self, facts, code):
        assert _dig(**facts) == code

    def test_the_message_names_the_disk(self):
        refused = actions.refusal(
            "dig_holes", status="ready", domains=[], storage_id="s1"
        )
        assert "s1" in refused[1]

    def test_unknown_perms_do_not_refuse(self):
        assert _dig(perms=None) is None

    def test_children_are_asked_with_the_deleted_ones(self):
        assert actions.spec("dig_holes").children_include_deleted
        assert not actions.spec("sparsify").children_include_deleted

    def test_no_other_action_grew_the_new_refusals(self):
        """A template's disk, a read-only one or an unused one stays sparsifiable."""
        for facts in (
            {"domains": [("template", "Stopped")]},
            {"perms": ["r"]},
            {"domains": []},
        ):
            assert (
                actions.refusal(
                    "sparsify",
                    status="ready",
                    has_children=lambda: False,
                    **{"perms": ["r", "w"], "domains": [DESKTOP], **facts},
                )
                is None
            )


def test_needs_domains_covers_every_domain_refusal():
    assert actions.needs_domains("dig_holes")
    assert actions.needs_domains("check_integrity")
    assert not actions.needs_domains("derive")


def test_allowed_actions_counts_deleted_children_only_for_dig_holes():
    allowed = actions.allowed_actions(
        status="ready",
        domains=[DESKTOP],
        has_deleted_children=True,
        perms=["r", "w"],
    )
    assert "dig_holes" not in allowed
    assert "sparsify" in allowed


def _query(monkeypatch, module, result):
    chain = MagicMock(name="query")
    for name in ("map", "get_all", "pluck", "filter", "table", "get", "default"):
        getattr(chain, name).return_value = chain
    chain.__getitem__.return_value = chain
    chain.run.return_value = result
    monkeypatch.setattr(module.r, "expr", lambda *a: chain)
    monkeypatch.setattr(module.r, "table", lambda *a: chain)


def test_search_info_carries_what_the_registry_admits(monkeypatch):
    _query(
        monkeypatch,
        lib,
        [
            {
                "id": "base",
                "perms": ["r"],
                "domains": [{"kind": "template", "status": "Stopped"}],
                "children": ["ready"],
            },
            {
                "id": "leaf",
                "perms": ["r", "w"],
                "domains": [{"kind": "desktop", "status": "Stopped"}],
                "children": [],
            },
            {
                "id": "orphaned-base",
                "perms": ["r", "w"],
                "domains": [{"kind": "desktop", "status": "Stopped"}],
                "children": ["deleted"],
            },
        ],
    )
    monkeypatch.setattr(
        lib.StorageProcessed, "_rdb_context", classmethod(lambda c: MagicMock())
    )
    base, leaf, orphaned = lib.StorageProcessed.add_allowed_actions(
        [
            {"id": "base", "status": "ready"},
            {"id": "leaf", "status": "ready"},
            {"id": "orphaned-base", "status": "ready"},
        ]
    )
    assert "dig_holes" not in base["allowed_actions"]
    assert "derive" in base["allowed_actions"]
    assert {"sparsify", "dig_holes", "delete"} <= set(leaf["allowed_actions"])
    assert "dig_holes" not in orphaned["allowed_actions"]
    assert "sparsify" in orphaned["allowed_actions"]
