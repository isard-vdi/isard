# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin queue pool does not probe a plain redis for maintenance notifications."""

from api.services.admin import queues


def test_the_admin_queue_pool_does_not_probe(monkeypatch):
    monkeypatch.setattr(queues, "_REDIS_POOL", None)

    config = queues._redis_pool().make_connection().maint_notifications_config

    assert config is None or config.enabled is False
