# SPDX-License-Identifier: AGPL-3.0-or-later

"""Redis clients built outside shared_client() do not probe for maint notifications."""

import importlib

import pytest

URL = "redis://:secret@redis.invalid:6379/3"

SOCKETIO_WRITERS = [
    "isardvdi_common.helpers.api_notify",
    "isardvdi_common.lib.domains.desktops.desktop_viewers",
    "isardvdi_common.lib.domains.desktops.desktop_direct_viewer",
    "isardvdi_common.lib.domains.desktops.desktops",
    "isardvdi_common.lib.domains.desktops.desktops_nonpersistent",
]


def _disabled(config):
    return config is None or config.enabled is False


def _probes(client):
    config = client.connection_pool.make_connection().maint_notifications_config
    return not _disabled(config)


def test_the_task_cancel_watcher_does_not_probe():
    from isardvdi_common.helpers.task_cancel import TaskCancelWatcher

    assert not _probes(TaskCancelWatcher("task-id")._conn)


def test_the_socketio_writer_does_not_probe():
    from isardvdi_common.connections import redis_client

    manager = redis_client.socketio_writer(URL)
    manager._redis_connect()

    assert manager.write_only is True
    assert not _probes(manager.redis)


@pytest.mark.parametrize("module", SOCKETIO_WRITERS)
def test_every_socketio_writer_turns_the_probe_off(module):
    options = importlib.import_module(module).socketio.redis_options

    assert "maint_notifications_config" in options
    assert _disabled(options["maint_notifications_config"])
