# SPDX-License-Identifier: AGPL-3.0-or-later

"""Incremental backing index for the purge guard, shared across workers via Redis."""

import json
import os
import random
import time

DEFAULT_KEY = os.environ.get(
    "STORAGE_PURGE_BIDX_KEY", "storage:purge_backing_index:entries"
)
DEFAULT_TTL_S = int(os.environ.get("STORAGE_PURGE_BIDX_TTL_S") or 6 * 3600)
DEFAULT_FLUSH = int(os.environ.get("STORAGE_PURGE_BIDX_FLUSH") or 200)
_HDEL_BATCH = 1000


def file_signature(path):
    # mtime_ns: a rebase -u rewrites the backing in place without changing size
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def _decode(value):
    return value.decode() if isinstance(value, (bytes, bytearray)) else value


def _load_hash(redis, key):
    try:
        raw = redis.hgetall(key) or {}
    except Exception:
        return {}
    return {_decode(k): v for k, v in raw.items()}


def _reusable(raw, sig):
    """The cached entry iff its signature matches and it was readable, else None."""
    if raw is None or sig is None:
        return None
    try:
        item = json.loads(_decode(raw))
        entry = item["e"]
        if item.get("sig") == sig and entry.get("readable"):
            return entry
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    return None


def _flush(redis, key, chunk, sigs, ttl_s):
    if redis is None:
        return
    # Never cache an unreadable entry: it must be re-read until it reads.
    mapping = {
        p: json.dumps({"sig": sigs.get(p), "e": e})
        for p, e in chunk.items()
        if e.get("readable") and sigs.get(p) is not None
    }
    try:
        if mapping:
            redis.hset(key, mapping=mapping)
        redis.expire(key, ttl_s)
    except Exception:
        pass


def _reclaim(redis, key, paths, sigs):
    """Entries a sibling worker flushed for *paths* since we started."""
    if redis is None or not paths:
        return {}
    try:
        values = redis.hmget(key, paths)
    except Exception:
        return {}
    out = {}
    for p, raw in zip(paths, values):
        entry = _reusable(raw, sigs.get(p))
        if entry is not None:
            out[p] = entry
    return out


def _prune_vanished(redis, key, cached, seen):
    if redis is None or not cached:
        return
    gone = [k for k in cached if k not in seen]
    for i in range(0, len(gone), _HDEL_BATCH):
        try:
            redis.hdel(key, *gone[i : i + _HDEL_BATCH])
        except Exception:
            return


def shared_backing_index(
    candidates_fn,
    build_fn,
    redis,
    *,
    key=None,
    ttl_s=DEFAULT_TTL_S,
    flush=DEFAULT_FLUSH,
    shuffle=True,
    log=None,
):
    """Build the backing index, reusing cached headers whose (mtime_ns, size) still match."""
    if key is None:
        key = DEFAULT_KEY
    started = time.monotonic()
    cached = _load_hash(redis, key) if redis is not None else {}

    index, missing, sigs = {}, [], {}
    for p in candidates_fn():
        sig = file_signature(p)
        sigs[p] = sig
        entry = _reusable(cached.get(p), sig)
        if entry is not None:
            index[p] = entry
        else:
            missing.append(p)
    reused = len(index)
    if shuffle:
        random.shuffle(missing)  # concurrent workers diverge and split the reads

    i = 0
    while i < len(missing):
        chunk = build_fn(missing[i : i + flush])
        index.update(chunk)
        _flush(redis, key, chunk, sigs, ttl_s)
        i += flush
        if redis is not None and i < len(missing):
            # Drop what a sibling flushed while we read our chunk.
            remaining = missing[i:]
            reclaimed = _reclaim(redis, key, remaining, sigs)
            if reclaimed:
                index.update(reclaimed)
                missing = missing[:i] + [p for p in remaining if p not in reclaimed]

    _prune_vanished(redis, key, cached, sigs)

    if log is not None:
        log(
            "purge backing index: %d files, %d reused, %d read, redis=%s, %.1fs"
            % (
                len(sigs),
                reused,
                len(missing),
                "up" if redis is not None else "down",
                time.monotonic() - started,
            )
        )
    return index
