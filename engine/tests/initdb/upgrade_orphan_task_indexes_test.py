# SPDX-License-Identifier: AGPL-3.0-or-later

"""The upgrade drops the task index of a storage/media row that no longer exists."""

import ast
import fnmatch
import runpy
import types

from tests.helpers import SRC_ROOT

m = types.SimpleNamespace(
    **runpy.run_path(
        str(SRC_ROOT / "initdb" / "upgrade_helpers.py"),
        run_name="_orphan_task_indexes_under_test",
    )
)


class FakeRedis:
    def __init__(self, keys):
        self.keys = {k.encode(): {"job": 1.0} for k in keys}
        self.unlinked = []

    def scan_iter(self, match, count):
        assert count >= 1000
        for key in list(self.keys):
            if fnmatch.fnmatchcase(key.decode(), match):
                yield key

    def unlink(self, *keys):
        self.unlinked.append(len(keys))
        for key in keys:
            self.keys.pop(key, None)


class FakeDB:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def existing_ids(self, table, ids):
        self.calls.append((table, len(ids)))
        return {i for i in ids if i in self.tables.get(table, {})}


def _run(keys, tables, chunk_size=500):
    redis = FakeRedis(keys)
    db = FakeDB(tables)
    result = m.drop_orphan_task_indexes(lambda: redis, db.existing_ids, chunk_size)
    return result, {k.decode() for k in redis.keys}, redis, db


def test_the_index_of_a_disk_that_no_longer_exists_is_dropped():
    result, left, _, _ = _run(["storage:gone:tasks"], {"storage": {}})
    assert result == (1, 1)
    assert left == set()


def test_the_index_of_a_disk_that_exists_is_kept_even_if_deleted():
    tables = {"storage": {"alive": "ready", "binned": "deleted"}}
    keys = ["storage:alive:tasks", "storage:binned:tasks", "storage:gone:tasks"]
    result, left, _, _ = _run(keys, tables)
    assert result == (3, 1)
    assert left == {"storage:alive:tasks", "storage:binned:tasks"}


def test_media_indexes_follow_the_media_table():
    tables = {"media": {"iso": "ready", "old": "deleted"}, "storage": {"iso2": "x"}}
    keys = [f"media:{i}:tasks" for i in ("iso", "old", "gone", "iso2")]
    result, left, _, _ = _run(keys, tables)
    assert result == (4, 2)
    assert left == {"media:iso:tasks", "media:old:tasks"}


def test_other_keys_are_never_touched():
    keys = ["storage:a:b:tasks", "storage:gone:other", "rq:job:x", "media::tasks"]
    result, left, _, _ = _run(keys, {})
    assert result == (0, 0)
    assert left == set(keys)


def test_lookups_and_unlinks_are_batched():
    keys = [f"storage:gone-{i}:tasks" for i in range(1201)]
    result, left, redis, db = _run(keys, {"storage": {}}, chunk_size=500)
    assert result == (1201, 1201)
    assert left == set()
    assert [n for t, n in db.calls if t == "storage"] == [500, 500, 201]
    assert redis.unlinked == [500, 500, 201]


def test_a_redis_failure_does_not_stop_the_upgrade():
    def _down():
        raise ConnectionError("redis is down")

    assert m.drop_orphan_task_indexes(_down, FakeDB({}).existing_ids) is None


def test_a_database_failure_does_not_stop_the_upgrade():
    def _broken(table, ids):
        raise RuntimeError("db is down")

    redis = FakeRedis(["storage:gone:tasks"])
    assert m.drop_orphan_task_indexes(lambda: redis, _broken) is None
    assert set(redis.keys) == {b"storage:gone:tasks"}


def test_the_upgrade_runs_it_in_the_redis_cleanup_step():
    tree = ast.parse((SRC_ROOT / "initdb" / "upgrade.py").read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "redis_tasks_cleanup"
    )
    called = {
        c.func.id
        for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "drop_orphan_task_indexes" in called
