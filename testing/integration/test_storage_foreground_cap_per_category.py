# SPDX-License-Identifier: AGPL-3.0-or-later

"""One category fills only its share of a foreground storage lane; another keeps entering."""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import pytest

from .helpers.client import IsardClient
from .helpers.waits import poll_for

rethinkdb = pytest.importorskip("rethinkdb")
redis = pytest.importorskip("redis")
from rethinkdb import r  # noqa: E402

SEEDED_TEMPLATE_ID = "template-test-001"  # seeded with a real qcow2
POOL = "00000000-0000-0000-0000-000000000000"
LANE = f"rq:queue:storage.{POOL}.interactive"
JOBCAT = "storage:jobcat:"
PASSWORD = "Cap-Share-Test-9!"
# the coverage index outlives a paused worker by STORAGE_COV_TTL_S (15 s); past it
# the lane reads as a fleet gap and admits everything
FLOOD_BUDGET_S = 12
DRAIN_TIMEOUT = int(os.environ.get("E2E_CAP_DRAIN_TIMEOUT", "300"))


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    try:
        return r.connect(
            host=host, port=port, db=os.environ.get("RETHINKDB_DB", "isard")
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _redis():
    password = os.environ.get("REDIS_PASSWORD")
    if not password:
        pytest.skip("needs REDIS_PASSWORD to read the storage lanes")
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        password=password,
    )


def _docker(*argv: str) -> str:
    if shutil.which("docker") is None:
        pytest.skip("needs docker to pause isard-storage")
    return subprocess.run(
        ["docker", *argv], capture_output=True, text=True, timeout=60, check=True
    ).stdout.strip()


def _apiv4_int(name: str, default: int) -> int:
    value = subprocess.run(
        ["docker", "exec", "isard-apiv4", "printenv", name],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return int(value) if value else default


def _owner(client: IsardClient, name: str) -> tuple[str, str]:
    category = client.post(
        "/api/v4/admin/item/category",
        json_body={"name": name, "description": "cap", "manager_permissions": {}},
    )["id"]
    group = client.post(
        "/api/v4/admin/item/group",
        json_body={"name": name, "description": "cap", "parent_category": category},
    )["id"]
    user = client.post(
        "/api/v4/admin/item/user",
        json_body={
            "username": name,
            "name": name,
            "provider": "local",
            "category": category,
            "group": group,
            "role": "advanced",
            "password": PASSWORD,
        },
    )
    return category, user["id"] if isinstance(user, dict) else user


def _queued(rq, category: str) -> int:
    ids = rq.lrange(LANE, 0, -1)
    if not ids:
        return 0
    cats = rq.mget([JOBCAT + i.decode() for i in ids])
    return sum(1 for c in cats if c and c.decode() == category)


def _flood(client: IsardClient, parent: str, user_id: str, created: list) -> dict:
    """Create disks for ``user_id`` until the lane refuses one; the refusal's body."""

    def one(_):
        resp = client.raw(
            "POST",
            "/api/v4/item/storage/priority/default",
            json={
                "usage": "desktop",
                "storage_type": "qcow2",
                "parent": parent,
                "size": "1G",
                "user_id": user_id,
            },
        )
        if resp.status_code == 200:
            created.append(resp.json()["storage_id"])
            return None
        return resp

    # one at a time: the share is checked before the enqueue, so concurrent
    # requests could each pass it
    for i in range(400):
        refused = one(i)
        if refused is not None:
            assert refused.status_code == 429, refused.text
            return refused.json()
    pytest.fail("the lane never refused a disk")


@pytest.mark.real
@pytest.mark.slow
def test_a_category_fills_only_its_share_and_another_reaches_the_global_cap(
    admin_client: IsardClient, test_namespace: str
):
    conn = _connect()
    rq = _redis()
    global_cap = _apiv4_int("STORAGE_SHED_HARD_INTERACTIVE", 60)
    share = _apiv4_int("STORAGE_SHED_CAT_HARD_INTERACTIVE", max(1, global_cap * 2 // 3))
    parent = (
        r.table("domains")
        .get(SEEDED_TEMPLATE_ID)["create_dict"]["hardware"]["disks"][0]["storage_id"]
        .run(conn)
    )
    cat_a, user_a = _owner(admin_client, f"{test_namespace}cap_a")
    cat_b, user_b = _owner(admin_client, f"{test_namespace}cap_b")
    assert rq.llen(LANE) == 0, "the interactive lane is not idle; run on a quiet stack"
    created: list[str] = []
    paused = False
    try:
        _docker("pause", "isard-storage")
        paused = True
        started = time.monotonic()

        first = _flood(admin_client, parent, user_a, created)
        assert first["description_code"] == "storage_overloaded_retry_later", first
        assert "full share" in first["description"], first
        assert _queued(rq, cat_a) == share

        second = _flood(admin_client, parent, user_b, created)
        elapsed = time.monotonic() - started
        assert elapsed < FLOOD_BUDGET_S, f"the flood took {elapsed:.1f}s"
        assert second["description_code"] == "storage_overloaded_retry_later", second
        assert "full share" not in second["description"], second
        # counted in the lane, not as accepted: a consumer elsewhere may take some
        assert _queued(rq, cat_a) + _queued(rq, cat_b) == global_cap
        assert _queued(rq, cat_b) == global_cap - share

        _docker("unpause", "isard-storage")
        paused = False
        poll_for(
            lambda: rq.llen(LANE),
            accept=lambda n: n == 0,
            timeout=DRAIN_TIMEOUT,
            interval=2.0,
            message="the interactive lane did not drain after the pause",
        )
    finally:
        if paused:
            _docker("unpause", "isard-storage")
        for storage_id in created:
            poll_for(
                lambda: r.table("storage")
                .get(storage_id)["status"]
                .default(None)
                .run(conn),
                accept=lambda s: s != "creating",
                timeout=DRAIN_TIMEOUT,
                interval=1.0,
                message=f"storage {storage_id} stayed creating",
            )
            admin_client.raw("DELETE", f"/api/v4/item/storage/{storage_id}")
        conn.close()
