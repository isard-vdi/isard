# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/storage_migration.py — the admin storage-disk migration
endpoints (plan / create / list / status / control / config + pool aggregation).

Ledger CRUD (list, status, control, config) runs the REAL service against the
mock DB. The three endpoints that need live ``Storage`` chain traversal (plan,
create, pool aggregation) mock at the ``isardvdi_common.lib.storage.migration``
boundary — that compute/DB layer is unit- and live-tested separately.
"""

import pytest
from tests.routes.helpers import MockJWT

ADMIN = MockJWT(role_id="admin")


def _migration(id="mig-1", status="planned", **extra):
    return {
        "id": id,
        "status": status,
        "selection": {"kind": "pool", "dst_pool_id": "dst"},
        "config": {"bwlimit_kbs": 0, "parallelism": 1, "verify": True},
        "totals": {},
        "created_by": "admin",
        "created_at": 1.0,
        "updated_at": 1.0,
        **extra,
    }


def _item(id, migration_id="mig-1", tree_id="r", storage_id=None, state="pending", **e):
    return {
        "id": id,
        "migration_id": migration_id,
        "storage_id": storage_id or id,
        "tree_id": tree_id,
        "topo_index": 0,
        "kind": "template",
        "state": state,
        "size_bytes": 10,
        "bytes_done": 0,
        "checkpoints": [],
        **e,
    }


def _pool(id="dst"):
    return {
        "id": id,
        "name": id,
        "mountpoint": f"/isard/{id}",
        "paths": {"desktop": [{"path": "desktops", "weight": 100}]},
        "categories": ["default"],
    }


# ── list ──────────────────────────────────────────────────────────────────
class TestList:
    URL = "/admin/storage/migrations"

    def test_admin_lists_migrations(self, test_client):
        resp = test_client(
            url=self.URL,
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(), _migration("mig-2")]},
        )
        assert resp.status_code == 200
        ids = {m["id"] for m in resp.json()["migrations"]}
        assert ids == {"mig-1", "mig-2"}

    def test_user_forbidden(self, test_client):
        resp = test_client(
            url=self.URL,
            jwt=MockJWT(role_id="user"),
            db_tables_data={"storage_migration": [_migration()]},
        )
        assert resp.status_code == 403

    def test_list_ordered_by_created_at_desc(self, test_client):
        # Newest first, stable. Seeded ascending so an unordered get_all would
        # come back ascending; the endpoint must return descending.
        resp = test_client(
            url=self.URL,
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [
                    _migration("old", created_at=100.0),
                    _migration("mid", created_at=200.0),
                    _migration("new", created_at=300.0),
                ]
            },
        )
        assert resp.status_code == 200
        migs = resp.json()["migrations"]
        assert [m["id"] for m in migs] == ["new", "mid", "old"]
        cas = [m["created_at"] for m in migs]
        assert cas == sorted(cas, reverse=True)

    def test_list_exposes_last_activity_at(self, test_client):
        resp = test_client(
            url=self.URL,
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [
                    _migration("a", created_at=2.0, last_activity_at=42.0),
                    _migration("b", created_at=1.0),  # absent -> None, not a crash
                ]
            },
        )
        assert resp.status_code == 200
        by_id = {m["id"]: m for m in resp.json()["migrations"]}
        assert by_id["a"]["last_activity_at"] == 42.0
        assert by_id["b"]["last_activity_at"] is None

    def test_list_row_is_enriched_and_carries_no_disks(self, test_client):
        # the row renders without a per-job GET /{id}: it carries the live fields
        # (eta/window/recurring/days/state_counts) but never the disks or trees.
        resp = test_client(
            url=self.URL,
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration()]},
        )
        assert resp.status_code == 200
        row = resp.json()["migrations"][0]
        for k in ("eta_seconds", "current_window", "recurring", "days", "state_counts"):
            assert k in row
        assert "items" not in row and "trees" not in row


# ── status ────────────────────────────────────────────────────────────────
class TestStatus:
    def test_status_aggregates_item_states(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1?items=true",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("mig-1--a", state="released"),
                    _item("mig-1--b", state="released"),
                    _item("mig-1--c", state="moving"),
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "mig-1"
        assert body["totals"]["items_total"] == 3
        assert body["totals"]["state_counts"]["released"] == 2
        # P2.6 aggregate enrichments used by the admin UI
        assert body["totals"]["done"] == 2  # two released
        assert body["eta_seconds"] is None  # no throughput sample yet
        assert {i["storage_id"] for i in body["items"]} == {
            "mig-1--a",
            "mig-1--b",
            "mig-1--c",
        }
        assert body["trees"][0]["done"] == 2

    def test_status_carries_dates(self, test_client):
        # both date columns come off the status aggregate (shared with the socket).
        resp = test_client(
            url="/admin/storage/migrations/mig-1",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [
                    _migration(created_at=111.0, last_activity_at=222.0)
                ],
                "storage_migration_item": [_item("mig-1--a", state="released")],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_at"] == 111.0
        assert body["last_activity_at"] == 222.0

    def test_status_omits_items_by_default(self, test_client):
        # the disks are served paginated by /items now; status stays light unless
        # ?items=true is asked (CSV/audit path).
        resp = test_client(
            url="/admin/storage/migrations/mig-1",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [_item("mig-1--a", state="released")],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []  # opt-in only
        assert body["trees"]  # trees still present for backward compatibility

    def test_status_missing_404(self, monkeypatch, test_client):
        # Mock the DB-boundary existence check (the mock DB engine can't model
        # a missing-doc lookup) to exercise the real service not_found -> 404.
        monkeypatch.setattr(
            "isardvdi_common.models.storage_migration.StorageMigration.exists",
            staticmethod(lambda mid: False),
        )
        resp = test_client(
            url="/admin/storage/migrations/ghost",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration()]},
        )
        assert resp.status_code == 404


# ── trees (paginated / filterable) ──────────────────────────────────────────
class TestTrees:
    def test_trees_paginated(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/trees?page=1&per_page=2",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("t0", tree_id="t0"),
                    _item("t1", tree_id="t1"),
                    _item("t2", tree_id="t2"),
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["trees"]) == 2

    def test_trees_state_filter(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/trees?state=moving",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("t0", tree_id="t0", state="pending"),
                    _item("m", tree_id="m", state="moving"),
                ],
            },
        )
        assert resp.status_code == 200
        assert [t["tree_id"] for t in resp.json()["trees"]] == ["m"]


# ── items (paginated / filterable / tree-scoped) ────────────────────────────
class TestItems:
    def test_items_scoped_to_tree(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/items?tree_id=r",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("a", tree_id="r"),
                    _item("b", tree_id="r"),
                    _item("c", tree_id="other"),
                ],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {i["storage_id"] for i in body["items"]} == {"a", "b"}

    def test_items_paginated(self, test_client):
        items = [_item(f"d{i}", tree_id="r") for i in range(5)]
        resp = test_client(
            url="/admin/storage/migrations/mig-1/items?tree_id=r&page=1&per_page=2",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": items,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 5
        assert len(resp.json()["items"]) == 2

    def test_items_state_filter(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/items?state=failed",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("a", state="released"),
                    _item("b", state="failed"),
                ],
            },
        )
        assert resp.status_code == 200
        assert {i["storage_id"] for i in resp.json()["items"]} == {"b"}


# ── control (start / pause / cancel) ────────────────────────────────────────
class TestControl:
    def test_start_sets_running(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/start",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_start_stamps_last_activity(self, test_client):
        # an API action stamps last_activity_at too, so even a job that never
        # moved a disk carries a timestamp for the table's Last-activity column.
        resp = test_client(
            url="/admin/storage/migrations/mig-1/start",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["last_activity_at"] is not None

    def test_cancel_running_finishes_current_tree(self, test_client):
        # cancel = finish-current-tree: a running job drains its in-flight tree
        # (and restores autostart) via finishing_tree before becoming canceled.
        resp = test_client(
            url="/admin/storage/migrations/mig-1/cancel",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(status="running")]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "finishing_tree"

    def test_cancel_unstarted_is_immediate(self, test_client):
        # a job that never started has nothing to finish -> canceled outright
        resp = test_client(
            url="/admin/storage/migrations/mig-1/cancel",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "canceled"

    def test_action_on_terminal_job_conflicts(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/start",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration(status="completed")]},
        )
        assert resp.status_code == 428

    def test_invalid_action_rejected_by_literal(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/teleport",
            method="POST",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration()]},
        )
        # the app maps RequestValidationError (bad Literal path param) to 400
        assert resp.status_code == 400


# ── config ──────────────────────────────────────────────────────────────────
class TestConfig:
    def test_update_config(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 5000, "parallelism": 2, "verify": False},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["bwlimit_kbs"] == 5000 and cfg["parallelism"] == 2
        assert resp.json()["last_activity_at"] is not None

    def test_a_partial_update_keeps_what_it_does_not_send(self, test_client):
        """Raising the parallelism of a running job used to reset every field
        it did not carry to its default: failure_policy back to
        retry_quarantine and the free-space floor to 0, in silence."""
        running = _migration(status="running")
        running["config"] = {
            "parallelism": 1,
            "failure_policy": "pause",
            "min_free_bytes": 10**9,
            "verify": True,
        }
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"parallelism": 2},
            db_tables_data={"storage_migration": [running]},
        )
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["parallelism"] == 2
        assert cfg["failure_policy"] == "pause"
        assert cfg["min_free_bytes"] == 10**9
        # a partial update returns current+changes, never a defaults-backfilled
        # config: backfilling would silently rewrite a pre-upgrade job (see the
        # legacy no-backfill test)
        assert cfg == {**running["config"], "parallelism": 2}

    def test_weakening_a_guarantee_needs_an_explicit_confirmation(self, test_client):
        running = _migration(status="running")
        running["config"] = {"parallelism": 1, "min_free_bytes": 10**9}
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"min_free_bytes": 0},
            db_tables_data={"storage_migration": [running]},
        )
        assert resp.status_code == 428
        assert "min_free_bytes" in resp.text
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"min_free_bytes": 0, "confirm_weakening": True},
            db_tables_data={"storage_migration": [running]},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["min_free_bytes"] == 0

    def test_verify_cannot_be_turned_off_on_a_job_that_moved(self, test_client):
        running = _migration(status="running")
        running["config"] = {"parallelism": 1, "verify": True}
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"verify": False, "confirm_weakening": True},
            db_tables_data={"storage_migration": [running]},
        )
        assert resp.status_code == 428
        assert "verify" in resp.text
        # the same value it already has is not a change
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"verify": True},
            db_tables_data={"storage_migration": [running]},
        )
        assert resp.status_code == 200

    def test_a_planned_job_may_still_change_verify(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"verify": False},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["verify"] is False

    def test_every_config_field_has_a_declared_policy(self):
        from api.schemas.admin.storage_migration import MigrationConfigData
        from isardvdi_common.lib.storage import migration as mig

        missing = set(MigrationConfigData.model_fields) - set(mig.CONFIG_FIELD_POLICY)
        assert not missing, f"fields without a live-change policy: {missing}"

    def test_partial_update_on_a_legacy_job_does_not_backfill_new_fields(
        self, test_client
    ):
        # a pre-upgrade job's config predates source_disposition / min_free_pct /
        # on_damaged / usage_age_days / load_policy; editing one field must not
        # backfill their defaults, or an absent source_disposition (legacy park)
        # would silently become "system" and follow the global delete_action.
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"parallelism": 4},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["parallelism"] == 4
        for f in (
            "source_disposition",
            "min_free_pct",
            "on_damaged",
            "usage_age_days",
            "include_never_used",
            "load_policy",
        ):
            assert f not in cfg, f"{f} was backfilled onto a legacy job's config"

    def test_config_on_terminal_job_conflicts(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [_migration(status="canceled")]},
        )
        assert resp.status_code == 428

    @pytest.mark.parametrize("value", ["pause", "continue"])
    def test_config_accepts_on_damaged(self, test_client, value):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"on_damaged": value},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["on_damaged"] == value

    def test_config_does_not_backfill_on_damaged(self, test_client):
        # Unlike source_disposition, absent and "pause" mean the same thing here
        # (the runner reads ``config.get("on_damaged") or "pause"``), so not
        # writing the default costs nothing and keeps the partial update partial.
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert "on_damaged" not in resp.json()["config"]

    def test_config_keeps_a_chosen_on_damaged(self, test_client):
        job = _migration(status="planned")
        job["config"]["on_damaged"] = "continue"
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [job]},
        )
        assert resp.json()["config"]["on_damaged"] == "continue"

    def test_config_rejects_an_unknown_on_damaged(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"on_damaged": "ignore"},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400

    def test_config_rejects_out_of_range_parallelism(self, test_client):
        # parallelism=100000 would defeat the throttle and mass-flip rows to
        # maintenance — bounded server-side via Field(ge=1, le=...).
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"parallelism": 100000},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400

    def test_config_rejects_zero_parallelism(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"parallelism": 0},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400

    def test_config_rejects_negative_bwlimit(self, test_client):
        # negative bwlimit produces rsync --bwlimit=-N and fails every move
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": -1},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize("disposition", ["system", "recycle_bin", "delete"])
    def test_config_accepts_every_source_disposition(self, test_client, disposition):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"source_disposition": disposition, "verify": True},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["source_disposition"] == disposition

    def test_config_keeps_the_stored_source_disposition(self, test_client):
        job = _migration(status="planned")
        job["config"]["source_disposition"] = "system"
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [job]},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["source_disposition"] == "system"

    def test_config_does_not_backfill_the_source_disposition(self, test_client):
        # An absent source_disposition is the legacy park, not "system": writing
        # the default onto a pre-upgrade job would make it follow delete_action.
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 200
        assert "source_disposition" not in resp.json()["config"]

    def test_config_rejects_an_unknown_source_disposition(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"source_disposition": "shred"},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400

    def test_config_refuses_a_hard_delete_with_verify_off(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"source_disposition": "delete", "verify": False},
            db_tables_data={"storage_migration": [_migration(status="planned")]},
        )
        assert resp.status_code == 400
        assert "verify" in resp.text


# ── plan (mock the compute boundary) ────────────────────────────────────────
class TestPlan:
    def test_plan_preview(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item("r", state="pending", topo_index=0, kind="template"),
                    _item("d", tree_id="r", state="pending", kind="desktop"),
                ],
                {"trees": 1, "items_total": 2, "bytes_total": 20},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        resp = test_client(
            url="/admin/storage/migrations/plan",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool", "dst_pool_id": "dst"}},
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["trees"]) == 1
        assert body["trees"][0]["desktops"] == 1
        assert body["totals"]["items_total"] == 2

    def test_plan_keeps_what_the_walk_leaves_behind(self, monkeypatch, test_client):
        """Re-summarising after the media items are appended dropped the disks
        the selection does not move and the trees it could not place, so the
        preview approved a pool drain as complete while templates stayed."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        stay = [
            {
                "storage_id": "t",
                "kind": "template",
                "classified_by": "domain",
                "reason": "kind 'template' is not in the selected disk types (desktop)",
            }
        ]
        excluded = [
            {"root_id": "x", "storage_id": "x", "reason": "no path", "disks": 1}
        ]
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [_item("d", tree_id="r", state="pending", kind="desktop")],
                {
                    "not_moving_by_kind": {"template": 1},
                    "not_moving_total": 1,
                    "not_moving_disks": stay,
                    "excluded_trees": excluded,
                    "excluded_disks_total": 1,
                },
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        resp = test_client(
            url="/admin/storage/migrations/plan",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "dst_pool_id": "dst",
                    "item_kinds": ["desktop"],
                }
            },
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 200
        totals = resp.json()["totals"]
        assert totals["not_moving_by_kind"] == {"template": 1}
        assert totals["not_moving_total"] == 1
        assert totals["not_moving_disks"] == stay
        assert totals["excluded_trees"] == excluded
        assert totals["excluded_disks_total"] == 1

    def test_plan_requires_dst_pool(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/plan",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool"}},
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 400

    def test_plan_allows_same_pool_because_its_paths_can_differ(
        self, monkeypatch, test_client
    ):
        """A pool with several weighted paths per usage can move a disk within itself."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/dst/groups_b/r.qcow2",
                        dst_path="/isard/dst/groups_a/r.qcow2",
                    )
                ],
                {"items_total": 1, "bytes_total": 10},
            ),
        )
        resp = test_client(
            url="/admin/storage/migrations/plan",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "dst",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={"storage_pool": [_pool()], "media": []},
        )
        assert resp.status_code == 200


# ── create (mock the compute boundary, assert persistence) ───────────────────
class TestCreate:
    def test_create_persists_job_and_items(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [_item(f"{mid}--r", migration_id=mid, state="pending")],
                {"items_total": 1, "bytes_total": 10},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        # this asserts persistence, so pin the lane gate open: left ambient it
        # answers from whatever redis the runner happens to have. Unreachable it
        # fails open and the create returns 200; reachable and empty it is a
        # readable fact about an absent fleet and the create is a 429. Same
        # code, opposite verdicts, decided by a service this test does not care
        # about. The reject path is the sibling below.
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue, **k: ("ok", {}),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool", "dst_pool_id": "dst"}},
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "planned"
        assert body["id"]
        assert body["last_activity_at"] is not None  # create stamps it

    def test_create_refuses_a_plan_that_resolves_entirely_in_place(
        self, monkeypatch, test_client
    ):
        """The hazard is not the pool being the same but nothing moving: the release
        would delete the live source."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/dst/desktops/r.qcow2",
                        dst_path="/isard/dst/desktops/r.qcow2",
                    )
                ],
                {"items_total": 1, "bytes_total": 10},
            ),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "dst",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
                "media": [],
            },
        )
        assert resp.status_code == 400

    def test_create_allows_same_pool_when_a_disk_changes_path(
        self, monkeypatch, test_client
    ):
        """Draining one weighted path into another inside the same pool is a real move."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        f"{mid}--r",
                        migration_id=mid,
                        src_path="/isard/dst/groups_b/r.qcow2",
                        dst_path="/isard/dst/groups_a/r.qcow2",
                    )
                ],
                {"items_total": 1, "bytes_total": 10},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue, **k: ("ok", {}),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "dst",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
                "media": [],
            },
        )
        assert resp.status_code == 200

    def test_create_empty_selection_400(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: [],
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool", "dst_pool_id": "dst"}},
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
                "media": [],
            },
        )
        assert resp.status_code == 400

    def test_create_recurring_without_schedule_400(self, test_client):
        # a recurring job has no defined "occurrence" without a window -> reject
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {"kind": "pool", "dst_pool_id": "dst"},
                "config": {"recurring": True},
            },
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        assert resp.status_code == 400

    def test_create_refuses_a_hard_delete_with_verify_off(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {"kind": "pool", "dst_pool_id": "dst"},
                "config": {"source_disposition": "delete", "verify": False},
            },
        )
        assert resp.status_code == 400
        assert "verify" in resp.text

    def test_create_rejects_destination_no_worker_serves_the_move_lane(
        self, monkeypatch, test_client
    ):
        """A cross-pool move lane with no live consumer would leave the job queued for ever."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/src/r.qcow2",
                        dst_path="/isard/dst/r.qcow2",
                    )
                ],
                {"items_total": 1},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        # nothing in the fleet serves the lane: the shared gate says reject with
        # reason no_consumer, which is what check_no_consumer turns into its 429
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue: (
                "reject",
                {"reason": "no_consumer", "pool": "src:dst"},
            ),
        )
        # and no node DECLARES the pool either, so nothing will ever drain it
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.storage_pools.storage_pools."
            "StoragePoolsProcessed._pool_coverage_declared",
            classmethod(lambda cls, pool_id: 0),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "src",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool("src"), _pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        # 429, not 400: "nothing drains this lane" is retryable, and the fleet
        # already answers it that way everywhere else
        assert resp.status_code == 429

    def test_create_waits_instead_of_refusing_when_the_nodes_are_only_asleep(
        self, monkeypatch, test_client
    ):
        """An elastic fleet powers its nodes down: no live consumer, but the pool is
        still declared, so the job waits instead of being refused."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda selection, **k: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/src/r.qcow2",
                        dst_path="/isard/dst/r.qcow2",
                    )
                ],
                {"items_total": 1},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue: (
                "reject",
                {"reason": "no_consumer", "pool": "src:dst"},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.storage_pools.storage_pools."
            "StoragePoolsProcessed._pool_coverage_declared",
            classmethod(lambda cls, pool_id: 2),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "src",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool("src"), _pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        assert resp.status_code != 429

    def test_create_still_refuses_when_the_declaration_cannot_be_read(
        self, monkeypatch, test_client
    ):
        """Fail closed, like the gate itself: an unreadable declaration is not a served lane."""
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda selection, **k: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/src/r.qcow2",
                        dst_path="/isard/dst/r.qcow2",
                    )
                ],
                {"items_total": 1},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue: (
                "reject",
                {"reason": "no_consumer", "pool": "src:dst"},
            ),
        )

        def _boom(cls, pool_id):
            raise RuntimeError("rethinkdb is unreachable")

        monkeypatch.setattr(
            "isardvdi_common.lib.storage.storage_pools.storage_pools."
            "StoragePoolsProcessed._pool_coverage_declared",
            classmethod(_boom),
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "pool",
                    "src_pool_id": "src",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool("src"), _pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        assert resp.status_code == 429

    def test_create_rejects_all_in_place_400(self, monkeypatch, test_client):
        # path/category selection resolving entirely in-place (dst == src) moves
        # nothing while the release would delete the live source -> reject
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_plan_for_roots",
            lambda mid, roots, pool, **k: (
                [
                    _item(
                        "r",
                        src_path="/isard/dst/r.qcow2",
                        dst_path="/isard/dst/r.qcow2",
                    )
                ],
                {"items_total": 1},
            ),
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.build_media_plan",
            lambda mid, sel, pool, **k: [],
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={
                "selection": {
                    "kind": "path",
                    "path_prefix": "/isard/dst",
                    "dst_pool_id": "dst",
                }
            },
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [],
                "storage_migration_item": [],
            },
        )
        assert resp.status_code == 400

    def test_create_rejects_overlap_409(self, monkeypatch, test_client):
        # the new selection resolves to disk d1, already reserved by an active job
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.resolved_disk_ids",
            lambda sel: {"d1"},
        )
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.roots_for_selection",
            lambda sel: ["r"],
        )
        resp = test_client(
            url="/admin/storage/migrations",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool", "dst_pool_id": "dst"}},
            db_tables_data={
                "storage_pool": [_pool()],
                "storage_migration": [_migration(id="mig-x", status="running")],
                "storage_migration_item": [_item("d1", migration_id="mig-x")],
            },
        )
        assert resp.status_code == 409
        assert "mig-x" in resp.json()["description"]


# ── downloadable log ────────────────────────────────────────────────────────
def _audit_rec(sid="a", result="moved_ok", occ="initial", size=100):
    return {
        "occurrence": occ,
        "occurrence_time": 5.0,
        "storage_id": sid,
        "kind": "template",
        "tree_id": "r",
        "src_path": f"/old/{sid}.qcow2",
        "dst_path": f"/new/{sid}.qcow2",
        "result": result,
        "size_bytes": size,
        "error": None,
        "started_at": 1.0,
        "finished_at": 5.0,
    }


class TestLog:
    def test_log_csv_download(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/log?format=csv",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("a", state="released", audit=[_audit_rec("a")])
                ],
            },
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert "migration-mig-1.csv" in resp.headers["content-disposition"]
        body = resp.text
        assert "moved_ok" in body
        assert "# bytes_moved,100" in body
        assert "/new/a.qcow2" in body

    def test_log_json_download_with_summary(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/log?format=json",
            jwt=ADMIN,
            db_tables_data={
                "storage_migration": [_migration()],
                "storage_migration_item": [
                    _item("a", state="released", audit=[_audit_rec("a", size=100)]),
                    _item(
                        "b",
                        state="failed",
                        audit=[_audit_rec("b", result="failed", occ="d2", size=0)],
                    ),
                ],
            },
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        body = resp.json()
        assert body["summary"]["records"] == 2
        assert body["summary"]["bytes_moved"] == 100  # only moved_ok
        assert body["summary"]["counts"]["failed"] == 1
        assert body["summary"]["occurrences"] == 2  # initial + d2
        assert len(body["records"]) == 2

    def test_log_missing_migration_404(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.models.storage_migration.StorageMigration.exists",
            staticmethod(lambda mid: False),
        )
        resp = test_client(
            url="/admin/storage/migrations/ghost/log",
            jwt=ADMIN,
            db_tables_data={"storage_migration": [_migration()]},
        )
        assert resp.status_code == 404


# ── path-prefixes (mock the storage enumeration boundary) ───────────────────
class TestPathPrefixes:
    def test_path_prefixes(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration._enumerate_storages",
            lambda *a, **k: [
                {"directory_path": "/isard/b"},
                {"directory_path": "/isard/a"},
                {"directory_path": "/isard/a"},
            ],
        )
        resp = test_client(
            url="/admin/storage/migrations/path-prefixes",
            method="GET",
            jwt=ADMIN,
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 200
        assert resp.json()["prefixes"] == ["/isard/a", "/isard/b"]


# ── pool aggregation (mock the compute boundary) ────────────────────────────
class TestPoolPlan:
    def test_pool_plan(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.migration.pool_plan_summary",
            lambda pid, **k: {
                "pool_id": pid,
                "trees": [
                    {
                        "tree_id": "r",
                        "root_storage_id": "r",
                        "derivative_templates": 1,
                        "desktops": 2,
                        "media": 0,
                        "items_total": 4,
                        "bytes_total": 99,
                    }
                ],
                "totals": {"trees": 1, "items_total": 4, "bytes_total": 99},
            },
        )
        resp = test_client(
            url="/admin/storage-pool/dst/migration/plan",
            jwt=ADMIN,
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pool_id"] == "dst"
        assert body["trees"][0]["desktops"] == 2
