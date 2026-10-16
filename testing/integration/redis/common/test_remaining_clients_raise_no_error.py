# SPDX-License-Identifier: AGPL-3.0-or-later

"""The redis clients built outside shared_client() raise no ERR on a plain server."""

import redis as redis_lib
from isardvdi_common.connections.redis_urls import rq_url, socketio_url

ROUNDS = 5


def _errors():
    info = redis_lib.from_url(rq_url(), protocol=2).info("all")
    return info.get("errorstat_ERR", {}).get("count", 0)


def test_new_task_cancel_watchers_raise_no_error():
    from isardvdi_common.helpers.task_cancel import TaskCancelWatcher

    before = _errors()
    for _ in range(ROUNDS):
        watcher = TaskCancelWatcher("integration-no-maint")
        watcher._conn.ping()
        watcher._conn.close()

    assert _errors() - before == 0


def test_new_socketio_writers_raise_no_error():
    from isardvdi_common.connections.redis_client import socketio_writer

    before = _errors()
    for _ in range(ROUNDS):
        manager = socketio_writer(socketio_url())
        manager._redis_connect()
        manager.redis.ping()
        manager.redis.close()

    assert _errors() - before == 0
