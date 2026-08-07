# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/storage_migration.py — the admin storage-disk migration
endpoints (plan / create / list / status / control / config + pool aggregation).

Ledger CRUD (list, status, control, config) runs the REAL service against the
mock DB. The three endpoints that need live ``Storage`` chain traversal (plan,
create, pool aggregation) mock at the ``isardvdi_common.lib.storage.migration``
boundary — that compute/DB layer is unit- and live-tested separately.
"""

from api.routes.tests.helpers import MockJWT

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


# ── status ────────────────────────────────────────────────────────────────
class TestStatus:
    def test_status_aggregates_item_states(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1",
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

    def test_config_on_terminal_job_conflicts(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/mig-1/config",
            method="PUT",
            jwt=ADMIN,
            body={"bwlimit_kbs": 1},
            db_tables_data={"storage_migration": [_migration(status="canceled")]},
        )
        assert resp.status_code == 428

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

    def test_plan_requires_dst_pool(self, test_client):
        resp = test_client(
            url="/admin/storage/migrations/plan",
            method="POST",
            jwt=ADMIN,
            body={"selection": {"kind": "pool"}},
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 400

    def test_plan_rejects_same_src_and_dst_pool(self, test_client):
        # same-pool selection is a one-click data-loss path — reject server-side
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
            db_tables_data={"storage_pool": [_pool()]},
        )
        assert resp.status_code == 400


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

    def test_create_rejects_same_src_and_dst_pool(self, test_client):
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
            },
        )
        assert resp.status_code == 400

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

    def test_create_rejects_destination_no_worker_serves_the_move_lane(
        self, monkeypatch, test_client
    ):
        """A pool->pool migration whose cross-pool move lane has no live consumer
        enqueues every move onto a queue nobody drains: the disks never move, the
        migration reports ``running`` forever and nothing ever errors. Refuse it
        at create instead of stranding it."""
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
        # nothing in the fleet serves the lane: the shared gate says reject with
        # reason no_consumer, which is what check_no_consumer turns into its 429
        monkeypatch.setattr(
            "isardvdi_common.lib.queue_coverage.lane_shed_decision",
            lambda conn, queue: (
                "reject",
                {"reason": "no_consumer", "pool": "src:dst"},
            ),
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
