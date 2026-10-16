#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unregister idle storage lanes from ``rq:queues``, which RQ never prunes."""

import logging
import time

from isardvdi_common.lib.queue_tiers import parse_storage_queue

log = logging.getLogger(__name__)

RQ_QUEUES_KEY = "rq:queues"
_QUEUE_PREFIX = "rq:queue:"
_STORAGE_PREFIX = _QUEUE_PREFIX + "storage."
_REGISTRY_PREFIXES = ("rq:wip:", "rq:deferred:", "rq:scheduled:", "rq:failed:")
_WORKERS_BY_QUEUE = "rq:workers:"

LANE_GC_GRACE_SECONDS = 3600
LANE_GC_INTERVAL_SECONDS = 300
LANE_GC_LOCK_KEY = "governor:lane_gc:lock"
LANE_GC_IDLE_SINCE_KEY = "governor:lane_gc:idle_since"
LANE_GC_REMOVED_KEY = "governor:lane_gc:removed"
LANE_GC_WATCH_SECONDS = 86400

# KEYS: rq:queues, list, 4 registries, rq:workers:<lane>, idle-since, removed.
# Worker hashes are read undeclared: fine on standalone Redis, not on a cluster.
_REMOVE_IDLE_LANE_LUA = """
local idle = redis.call('LLEN', KEYS[2]) == 0
for i = 3, 6 do
  if idle and redis.call('ZCARD', KEYS[i]) > 0 then idle = false end
end
if idle then
  for _, worker in ipairs(redis.call('SMEMBERS', KEYS[7])) do
    if redis.call('EXISTS', worker) == 1 then idle = false break end
  end
end
redis.call('HDEL', KEYS[8], ARGV[1])
if not idle then return 0 end
local removed = redis.call('SREM', KEYS[1], ARGV[1])
if removed == 1 then redis.call('ZADD', KEYS[9], ARGV[2], ARGV[1]) end
return removed
"""

# KEYS: rq:queues, list, 4 registries, removed.
_RESTORE_LANE_LUA = """
if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
  redis.call('ZREM', KEYS[7], ARGV[1])
  return 0
end
local busy = redis.call('LLEN', KEYS[2]) > 0
for i = 3, 6 do
  if not busy and redis.call('ZCARD', KEYS[i]) > 0 then busy = true end
end
if not busy then return 0 end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[7], ARGV[1])
return 1
"""


def _text(value):
    return value.decode() if isinstance(value, (bytes, bytearray)) else value


def _lane_keys(lane_key):
    name = lane_key[len(_QUEUE_PREFIX) :]
    return [lane_key] + [prefix + name for prefix in _REGISTRY_PREFIXES]


def _storage_lanes(conn):
    lanes = []
    for raw in conn.smembers(RQ_QUEUES_KEY) or ():
        key = _text(raw)
        if key and key.startswith(_STORAGE_PREFIX):
            if parse_storage_queue(key[len(_QUEUE_PREFIX) :]):
                lanes.append(key)
    return sorted(lanes)


def _restore_removed_lanes(conn, now):
    """Re-register removed lanes that got work without an enqueue's SADD."""
    restored = 0
    conn.zremrangebyscore(LANE_GC_REMOVED_KEY, "-inf", now - LANE_GC_WATCH_SECONDS)
    for raw in conn.zrange(LANE_GC_REMOVED_KEY, 0, -1) or ():
        key = _text(raw)
        keys = [RQ_QUEUES_KEY] + _lane_keys(key) + [LANE_GC_REMOVED_KEY]
        if conn.eval(_RESTORE_LANE_LUA, len(keys), *keys, key):
            restored += 1
            log.warning("lane GC: %s got work after removal; registered again", key)
    return restored


def _idle_lanes(conn, lanes):
    with conn.pipeline() as pipe:
        for key in lanes:
            pipe.llen(key)
            for k in _lane_keys(key)[1:]:
                pipe.zcard(k)
            pipe.smembers(_WORKERS_BY_QUEUE + key[len(_QUEUE_PREFIX) :])
        raw = pipe.execute()

    per_lane = 2 + len(_REGISTRY_PREFIXES)
    has_work, listeners = {}, {}
    for i, key in enumerate(lanes):
        row = raw[i * per_lane : (i + 1) * per_lane]
        has_work[key] = any(row[:-1])
        listeners[key] = [_text(w) for w in (row[-1] or ())]

    workers = sorted({w for ws in listeners.values() for w in ws})
    alive = set()
    if workers:
        with conn.pipeline() as pipe:
            for w in workers:
                pipe.exists(w)
            alive = {w for w, ok in zip(workers, pipe.execute()) if ok}

    return {
        key: not has_work[key] and not any(w in alive for w in listeners[key])
        for key in lanes
    }


def collect_empty_lanes(conn, now=None, grace=LANE_GC_GRACE_SECONDS):
    """One fleet-wide rate-limited pass; returns a summary and never raises."""
    try:
        if not conn.set(LANE_GC_LOCK_KEY, "1", nx=True, ex=LANE_GC_INTERVAL_SECONDS):
            return {"skipped": True}
        return _collect(conn, time.time() if now is None else now, grace)
    except Exception:
        log.exception("lane GC: pass failed; rq:queues left as it was")
        return {"skipped": True, "error": True}


def _collect(conn, now, grace):
    summary = {"skipped": False, "busy": 0, "waiting": 0, "removed": 0}
    summary["restored"] = _restore_removed_lanes(conn, now)

    lanes = _storage_lanes(conn)
    summary["lanes"] = len(lanes)
    idle = _idle_lanes(conn, lanes) if lanes else {}
    idle_since = {
        _text(k): float(_text(v))
        for k, v in (conn.hgetall(LANE_GC_IDLE_SINCE_KEY) or {}).items()
    }

    due = []
    with conn.pipeline() as pipe:
        for key in lanes:
            if not idle[key]:
                summary["busy"] += 1
                if key in idle_since:
                    pipe.hdel(LANE_GC_IDLE_SINCE_KEY, key)
            elif key not in idle_since:
                summary["waiting"] += 1
                pipe.hset(LANE_GC_IDLE_SINCE_KEY, key, now)
            elif now - idle_since[key] < grace:
                summary["waiting"] += 1
            else:
                due.append(key)
        for key in set(idle_since) - set(lanes):
            pipe.hdel(LANE_GC_IDLE_SINCE_KEY, key)
        pipe.execute()

    for key in due:
        name = key[len(_QUEUE_PREFIX) :]
        keys = (
            [RQ_QUEUES_KEY]
            + _lane_keys(key)
            + [_WORKERS_BY_QUEUE + name, LANE_GC_IDLE_SINCE_KEY, LANE_GC_REMOVED_KEY]
        )
        if conn.eval(_REMOVE_IDLE_LANE_LUA, len(keys), *keys, key, now):
            summary["removed"] += 1
        else:
            summary["busy"] += 1

    if summary["removed"]:
        # RQ's enqueue SADDs and pushes in two round trips; catch one that
        # straddled a removal now rather than on the next pass.
        summary["restored"] += _restore_removed_lanes(conn, now)
        log.info("lane GC: %s", summary)
    return summary
