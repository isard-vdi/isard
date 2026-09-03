"""Unit tests for the self-re-registering worker mixin (no live RQ worker/redis).

Same construction as ``test_governed_worker.py``: ``object.__new__`` (skipping
the heavy ``Worker.__init__``) plus an in-memory fake Redis and a ``_FakePipeline``
that records commands and replays them on ``execute``. The fake here is a
separate, smaller one — the governor's fake models the heavy-slot SET and the
reserve Lua, none of which this module touches, and it has no ``sismember``.

What is under test is the gap RQ leaves open: ``worker_registration.register``
(the ``SADD rq:workers``) is called from exactly ONE place in all of RQ —
``register_birth()``, and only from ``bootstrap()`` at startup. ``heartbeat()``
does ``HSET last_heartbeat`` + ``EXPIRE`` and no ``SADD``, so once
``rq:worker:<name>`` has expired the heartbeat RECREATES the key with a single
field and rejoins NO set, while ``clean_worker_registry`` (every 10 min) sees
the key gone and evicts the worker from the global set for good. Final state:
``EXISTS rq:worker:<name>`` is 1, ``SISMEMBER rq:workers <key>`` is 0, and the
process happily keeps consuming jobs — invisible to every dashboard, which reads
that set and nothing else.
"""

import fnmatch
import logging

import pytest
from isardvdi_common.lib import registered_worker as rw
from rq import Worker, worker_registration
from rq.utils import now

WORKER_NAME = "storage-stdlane:isard-storage:3ae1fdcd"
WORKER_KEY = "rq:worker:" + WORKER_NAME
QUEUE_A = "storage.pool-a.standard"
QUEUE_B = "storage.pool-a.interactive"


class _FakeRedis:
    """In-memory hash + SET store with the expiry bookkeeping this module needs.
    ``exists`` honours the hash store (RQ's worker key IS a hash), and
    ``sismember`` counts its calls so the throttle can be asserted on."""

    def __init__(self):
        self._sets = {}
        self._hashes = {}
        self._expires = {}
        self.sismember_calls = 0

    def _s(self, key):
        return self._sets.setdefault(key, set())

    def sadd(self, key, *vals):
        s = self._s(key)
        added = 0
        for v in vals:
            if v not in s:
                s.add(v)
                added += 1
        return added

    def srem(self, key, *vals):
        s = self._sets.get(key)
        if not s:
            return 0
        removed = 0
        for v in vals:
            if v in s:
                s.discard(v)
                removed += 1
        return removed

    def smembers(self, key):
        return set(self._sets.get(key, ()))

    def sismember(self, key, val):
        self.sismember_calls += 1
        return val in self._sets.get(key, ())

    def hset(self, key, field=None, value=None, mapping=None):
        h = self._hashes.setdefault(key, {})
        if field is not None:
            h[field] = str(value)
        if mapping:
            h.update({k: str(v) for k, v in mapping.items()})
        return len(mapping or {}) + (1 if field is not None else 0)

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def hexists(self, key, field):
        return field in self._hashes.get(key, {})

    def exists(self, *keys):
        return sum(1 for k in keys if k in self._hashes or k in self._sets)

    def expire(self, key, ttl):
        self._expires[key] = ttl
        return True

    def ttl(self, key):
        return self._expires.get(key, -1)

    def delete(self, *keys):
        n = 0
        for k in keys:
            for store in (self._hashes, self._sets):
                if k in store:
                    del store[k]
                    n += 1
            self._expires.pop(k, None)
        return n

    def keys(self, pattern):
        return [k for k in self._hashes if fnmatch.fnmatch(k, pattern)]

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    """Records queued commands and replays them against the parent _FakeRedis on
    ``execute`` — matches redis-py's ``with conn.pipeline() as pipe:`` usage."""

    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        out = [
            getattr(self._redis, name)(*args, **kwargs)
            for (name, args, kwargs) in self._ops
        ]
        self._ops = []
        return out


class _Q:
    def __init__(self, name):
        self.name = name


class _TestWorker(rw.RegisteredWorker):
    pass


def _worker(connection, queues=(QUEUE_A, QUEUE_B)):
    """Build a worker without ``Worker.__init__`` (it wants a live queue), setting
    exactly the attributes the real ``heartbeat()`` / ``serialize()`` read."""
    w = object.__new__(_TestWorker)
    w.name = WORKER_NAME
    w.connection = connection
    w.queues = [_Q(q) for q in queues]
    w.worker_ttl = 420
    w.birth_date = now()
    w.last_heartbeat = now()
    w._state = "idle"
    w.pid = 4242
    w.hostname = "isard-storage"
    w.ip_address = "10.1.0.5"
    w.version = "2.10.0"
    w.python_version = "3.14.6"
    w.log = logging.getLogger("test-registered-worker")  # set by Worker.__init__
    return w


def _register(w):
    """Put the worker in the healthy state RQ leaves it in after bootstrap."""
    with w.connection.pipeline() as pipe:
        pipe.hset(w.key, mapping=w.serialize())
        pipe.hset(w.key, "state", w.get_state())
        worker_registration.register(w, pipe)
        pipe.expire(w.key, w.worker_ttl + 60)
        pipe.execute()


def _lose_registration(r, w):
    """The observed failure: the key expired (so RQ's periodic
    ``clean_worker_registry`` evicted it from both sets) — key gone, sets empty."""
    r.delete(w.key)
    r.srem(worker_registration.REDIS_WORKER_KEYS, w.key)
    for q in w.queue_names():
        r.srem(worker_registration.WORKERS_BY_QUEUE_KEY % q, w.key)


# --- 1. Recovery: the next heartbeat puts the worker back, unaided -----------


def test_heartbeat_restores_a_lost_registration():
    r = _FakeRedis()
    w = _worker(r)
    _register(w)
    _lose_registration(r, w)
    assert r.sismember(worker_registration.REDIS_WORKER_KEYS, w.key) is False

    w.heartbeat()

    # Back in the global set AND in every per-queue set (the dashboards read the
    # global one; ``Queue.all_workers`` and clean_worker_registry read per-queue).
    assert r.sismember(worker_registration.REDIS_WORKER_KEYS, w.key) is True
    for q in (QUEUE_A, QUEUE_B):
        assert w.key in r.smembers(worker_registration.WORKERS_BY_QUEUE_KEY % q)
    # ...with a real worker hash again, not the single-field husk a bare
    # heartbeat leaves behind.
    h = r.hgetall(w.key)
    assert h.get("birth")
    assert h.get("queues") == f"{QUEUE_A},{QUEUE_B}"
    assert h.get("state") == "idle"
    assert h.get("last_heartbeat")
    # ...and an expiry, or the key we just rewrote would leak forever.
    assert r.ttl(w.key) == w.worker_ttl + 60


# --- 2. Throttle: one check per window, not one per heartbeat ----------------


def test_registration_check_is_throttled_to_one_per_window(monkeypatch):
    r = _FakeRedis()
    w = _worker(r)
    _register(w)
    clock = [1000.0]
    monkeypatch.setattr(rw.time, "monotonic", lambda: clock[0])

    w.heartbeat()
    assert r.sismember_calls == 1

    # Second heartbeat inside the window: no second SISMEMBER.
    clock[0] += rw.REGISTRATION_CHECK_INTERVAL - 1
    w.heartbeat()
    assert r.sismember_calls == 1

    # Past the window: checked again.
    clock[0] += 2
    w.heartbeat()
    assert r.sismember_calls == 2


# --- 3. Costs nothing when the registration is healthy ----------------------


def test_healthy_registration_is_not_rewritten(monkeypatch):
    r = _FakeRedis()
    w = _worker(r)
    _register(w)
    calls = []
    monkeypatch.setattr(
        rw.worker_registration,
        "register",
        lambda *a, **k: calls.append(a),
    )

    w.heartbeat()

    assert calls == []


# --- 4. This can never take the work loop down ------------------------------


class _BoomRedis(_FakeRedis):
    """Fails one named command, but only once ``armed`` — so the healthy setup
    the test starts from can still be built through the same connection."""

    def __init__(self, command):
        super().__init__()
        self._command = command
        self.armed = False

    def _maybe_boom(self, name):
        if self.armed and name == self._command:
            raise RuntimeError("redis is down")

    def sismember(self, key, val):
        self._maybe_boom("sismember")
        return super().sismember(key, val)

    def sadd(self, key, *vals):
        self._maybe_boom("sadd")
        return super().sadd(key, *vals)

    def hset(self, key, field=None, value=None, mapping=None):
        self._maybe_boom("hset")
        return super().hset(key, field, value, mapping)


def test_heartbeat_swallows_a_redis_failure_in_the_check():
    r = _BoomRedis("sismember")
    w = _worker(r)
    _register(w)
    r.armed = True

    w.heartbeat()  # must not raise — a failed check is not a reason to die


def test_heartbeat_swallows_a_redis_failure_in_the_rewrite():
    r = _BoomRedis("sadd")
    w = _worker(r)
    _register(w)
    _lose_registration(r, w)
    r.armed = True

    w.heartbeat()  # must not raise


# --- 5. The cure must NOT go through register_birth() -----------------------


def test_register_birth_would_raise_on_a_live_key():
    """Why the cure cannot reuse RQ's own re-registration path: the observed
    failure leaves the KEY alive (only the set membership is gone), and
    ``register_birth`` refuses outright on a live key with no ``death`` field."""
    r = _FakeRedis()
    w = _worker(r)
    _register(w)

    with pytest.raises(ValueError):
        Worker.register_birth(w)


def test_recovery_never_calls_register_birth(monkeypatch):
    r = _FakeRedis()
    w = _worker(r)
    _register(w)
    _lose_registration(r, w)
    # Sabotage it: if the cure reaches for register_birth the test fails loudly
    # rather than passing by luck on a fake that happens to tolerate it.
    monkeypatch.setattr(
        rw.RegisteredWorker,
        "register_birth",
        lambda self: pytest.fail("the cure must not use register_birth()"),
    )

    w.heartbeat()

    assert r.sismember(worker_registration.REDIS_WORKER_KEYS, w.key) is True
