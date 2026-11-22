# SPDX-License-Identifier: AGPL-3.0-or-later

"""Mass disk actions that answer at once and run after, kept in redis so a restart resumes them."""

import json
import logging as log
import threading
import uuid

from isardvdi_common.helpers.api_notify import notify_admin
from isardvdi_common.models.task import Task

INDEX = "storage:batches"
TTL_S = 7 * 24 * 3600
LEASE_S = 60
EXAMPLES = 3
MAX_ATTEMPTS = 5

_ACTIONS = {}


def register(action, title, outcome):
    """Name an action: its notice ``title`` (with ``{status}``) and ``outcome(payload, storage_id)``."""
    _ACTIONS[action] = (title, outcome)


def _key(batch_id, part=""):
    return f"storage:batch:{batch_id}{part}"


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def _redis():
    return Task._redis


def start(payload, action, status, storage_ids):
    """Store the batch, start running it, and return how many distinct disks it takes."""
    if action not in _ACTIONS:
        raise ValueError(f"unknown storage batch action {action!r}")
    ids = list(dict.fromkeys(storage_ids))
    batch_id = uuid.uuid4().hex
    pipe = _redis().pipeline()
    pipe.hset(
        _key(batch_id),
        mapping={
            "action": action,
            "status": status,
            "payload": json.dumps(payload),
            "total": len(ids),
            "cursor": 0,
            "queued": 0,
            "attempts": 0,
        },
    )
    for i in range(0, len(ids), 1000):
        pipe.rpush(_key(batch_id, ":ids"), *ids[i : i + 1000])
    pipe.expire(_key(batch_id), TTL_S)
    pipe.expire(_key(batch_id, ":ids"), TTL_S)
    pipe.sadd(INDEX, batch_id)
    pipe.execute()
    _claim_and_spawn(batch_id)
    return len(ids)


def resume_all():
    """Start every stored batch whose runner is gone; drop the index entry of one that expired."""
    redis = _redis()
    for batch_id in [_text(b) for b in redis.smembers(INDEX)]:
        if not redis.exists(_key(batch_id)):
            redis.srem(INDEX, batch_id)
            continue
        _claim_and_spawn(batch_id)


def _claim_and_spawn(batch_id):
    owner = uuid.uuid4().hex
    if not _redis().set(_key(batch_id, ":lease"), owner, nx=True, ex=LEASE_S):
        return False
    _spawn(batch_id, owner)
    return True


def _spawn(batch_id, owner):
    threading.Thread(
        target=run, args=(batch_id, owner), daemon=True, name="storage-batch"
    ).start()


def summary(queued, total, refused, examples):
    """The queued count and one line per refusal reason, short at any batch size."""
    lines = [f"Queued on {queued} of {total} disk(s)."]
    for code, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        shown = examples.get(code, [])
        more = ", ..." if count > len(shown) else ""
        lines.append(f"{count} refused: {code} ({', '.join(shown)}{more})")
    return "\n".join(lines)


def run(batch_id, owner):
    """Run a batch from its cursor to the end, then tell the admin how it went and drop it."""
    redis = _redis()
    meta = {_text(k): _text(v) for k, v in redis.hgetall(_key(batch_id)).items()}
    if not meta:
        redis.srem(INDEX, batch_id)
        return
    payload = json.loads(meta["payload"])
    title, outcome = _ACTIONS[meta["action"]]
    title = title.format(status=meta["status"])
    cursor, total = int(meta["cursor"]), int(meta["total"])
    try:
        while cursor < total:
            if _text(redis.get(_key(batch_id, ":lease"))) != owner:
                log.warning("storage batch %s: another runner took it over", batch_id)
                return
            storage_id = _text(redis.lindex(_key(batch_id, ":ids"), cursor))
            _record(redis, batch_id, storage_id, outcome(payload, storage_id))
            cursor += 1
        _finish(redis, batch_id, payload["user_id"], title, total)
    except Exception:
        log.exception("storage batch %s stopped at %d of %d", batch_id, cursor, total)
        if redis.hincrby(_key(batch_id), "attempts", 1) < MAX_ATTEMPTS:
            notify_admin(
                payload["user_id"],
                title,
                f"Stopped at {cursor} of {total} disk(s); it resumes on its own.",
                type="warning",
            )
            return
        notify_admin(
            payload["user_id"],
            title,
            f"Stopped at {cursor} of {total} disk(s) and given up.",
            type="error",
            params={"hide": False},
        )
        _drop(redis, batch_id)


def _record(redis, batch_id, storage_id, result):
    code = (
        None if result.get("task_id") else result.get("description_code") or "unknown"
    )
    pipe = redis.pipeline()
    pipe.hincrby(_key(batch_id), "cursor", 1)
    if code is None:
        pipe.hincrby(_key(batch_id), "queued", 1)
    else:
        pipe.hincrby(_key(batch_id, ":refused"), code, 1)
        pipe.expire(_key(batch_id, ":refused"), TTL_S)
    pipe.expire(_key(batch_id, ":lease"), LEASE_S)
    replies = pipe.execute()
    if code is not None and replies[1] <= EXAMPLES:
        redis.hset(_key(batch_id, ":examples"), f"{code}:{replies[1]}", storage_id)
        redis.expire(_key(batch_id, ":examples"), TTL_S)


def _finish(redis, batch_id, user_id, title, total):
    queued = int(_text(redis.hget(_key(batch_id), "queued")) or 0)
    refused = {
        _text(k): int(v) for k, v in redis.hgetall(_key(batch_id, ":refused")).items()
    }
    examples = {}
    for field, storage_id in sorted(
        (_text(k), _text(v))
        for k, v in redis.hgetall(_key(batch_id, ":examples")).items()
    ):
        examples.setdefault(field.rsplit(":", 1)[0], []).append(storage_id)
    notify_admin(
        user_id,
        title,
        summary(queued, total, refused, examples),
        type="info" if refused else "success",
        params={"hide": not refused},
    )
    _drop(redis, batch_id)


def _drop(redis, batch_id):
    pipe = redis.pipeline()
    for part in ("", ":ids", ":refused", ":examples", ":lease"):
        pipe.delete(_key(batch_id, part))
    pipe.srem(INDEX, batch_id)
    pipe.execute()
