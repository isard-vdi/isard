# SPDX-License-Identifier: AGPL-3.0-or-later

"""Outside a job the worker reuses one redis client, which does not probe either."""


def test_outside_a_job_the_client_is_shared_and_does_not_probe(monkeypatch):
    from isardvdi_common.connections import redis_client
    from isardvdi_storage import task

    monkeypatch.setattr(redis_client, "_clients", {})
    monkeypatch.setattr(task, "get_current_job", lambda: None)

    first = task._redis_connection()
    config = first.connection_pool.make_connection().maint_notifications_config

    assert task._redis_connection() is first
    assert config is None or config.enabled is False
