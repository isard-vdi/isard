# SPDX-License-Identifier: AGPL-3.0-or-later

"""The migration claim must land in the per-owner task index.

Nothing else caught this: the runner enqueues its move/rebase/verify tasks
directly, bypassing ``create_task`` (the one other producer that indexes), so
``_claim_storage_task`` is the only thing that can record the saga's live task
where reconcile ``_task_alive``, ``abort_operations`` and the 428 gate read it.
Stamping only the retired ``task`` scalar leaves ``current_task_id`` answering
``None`` while the disk is in ``maintenance`` mid-move -- so the reconciler
promotes it out from under rsync and abort silently no-ops. The whole class of
defect shipped green because no test asserted the claim's effect on that reader;
this is that test.

Real redis: the claim fetches and scores a real rq job and writes a ZSET, none
of which a mocked connection can stand in for. Runs in CI (the ``unit-test-*``
jobs give it one) and skips locally when there is none -- never against db 0.
"""

import os

import pytest
import redis as redis_lib
from isardvdi_common.lib.storage.migration_run import MigrationRunner
from isardvdi_common.lib.task_index import current_task_id, index_key
from isardvdi_common.models.task import Task
from rq import Queue


def _redis_or_skip():
    url = os.environ.get("ISARD_TEST_REDIS")
    if url:
        connection = redis_lib.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    else:
        connection = redis_lib.Redis(
            host=os.environ.get("REDIS_HOST") or "isard-redis",
            port=int(os.environ.get("REDIS_PORT") or 6379),
            password=os.environ.get("REDIS_PASSWORD", ""),
            db=int(os.environ.get("TASK_CHAIN_TEST_REDIS_DB", "9")),
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    assert (
        connection.get_connection_kwargs().get("db") != 0
    ), "refusing to run against the rq db"
    try:
        connection.ping()
    except Exception as error:
        pytest.skip(f"no Redis for the migration-claim index test: {error}")
    return connection


def test_claim_records_the_task_in_the_owner_index():
    """After the claim, the reader every liveness check uses finds the task.

    Fails when the claim writes only ``.task`` (``current_task_id`` reads the
    index, so it answers ``None``); passes when the claim writes the index.
    """
    conn = _redis_or_skip()
    storage_id = "s-migration-claim-index-regression"
    idx = index_key("storage", storage_id)
    original = Task.__dict__.get("_redis")
    Task._redis = conn
    job = Queue("migration-claim-index-test", connection=conn).enqueue_call(
        func="builtins.len", args=([],)
    )
    try:
        conn.delete(idx)
        MigrationRunner.__new__(MigrationRunner)._claim_storage_task(
            {"storage_id": storage_id}, job.id
        )
        assert current_task_id(conn, storage_id) == job.id
    finally:
        conn.delete(idx)
        try:
            job.delete()
        except Exception:
            pass
        if original is None:
            del Task._redis
        else:
            Task._redis = original
