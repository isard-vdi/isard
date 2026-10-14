# Copyright 2026 the Isard-vdi project authors
# License: AGPLv3

"""Domains a hypervisor may still run because their last libvirt call never answered."""

import json
import threading
import time

from engine.services.log import logs

REDIS_KEY = "engine:held_domains"

_lock = threading.Lock()
_held = {}


def _mirror(domain_id, entry):
    try:
        from isardvdi_common.connections.redis_base import RedisBase

        if entry is None:
            RedisBase._redis.hdel(REDIS_KEY, domain_id)
        else:
            RedisBase._redis.hset(REDIS_KEY, domain_id, json.dumps(entry))
    except Exception as e:
        logs.workers.warning(f"Could not mirror the hold of {domain_id}: {e}")


def hold(domain_id, hyp_id, operation):
    entry = {"hyp_id": hyp_id, "operation": operation, "since": time.time()}
    with _lock:
        _held[domain_id] = entry
    _mirror(domain_id, entry)
    logs.workers.warning(
        f"[{hyp_id}] {domain_id} held: {operation} has not answered, "
        "the domain is not started anywhere until it does"
    )


def release(domain_id, hyp_id=None):
    with _lock:
        entry = _held.get(domain_id)
        if entry is None or (hyp_id is not None and entry["hyp_id"] != hyp_id):
            return False
        del _held[domain_id]
    _mirror(domain_id, None)
    logs.workers.info(
        f"[{entry['hyp_id']}] {domain_id} released ({entry['operation']})"
    )
    return True


def holder(domain_id):
    with _lock:
        entry = _held.get(domain_id)
        return dict(entry) if entry else None


def reset():
    with _lock:
        _held.clear()
    try:
        from isardvdi_common.connections.redis_base import RedisBase

        RedisBase._redis.delete(REDIS_KEY)
    except Exception as e:
        logs.workers.warning(f"Could not clear the held domains: {e}")
