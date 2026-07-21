"""Unit tests for GovernedWorker admission (no live RQ worker/redis).

Built with ``object.__new__`` (skipping the heavy ``Worker.__init__``) + a fake
Redis that models the heavy-slot SET and the atomic reserve Lua, plus a fake
``queue_class`` whose ``dequeue_any`` records the queue set RQ would actually
BLPOP and returns scripted results. The dequeue-path tests assert on that
queue set (what the worker really reads) and on actual admission — the
regression guard for the Phase-1 bug where the governor was inert and, once
that was fixed, the follow-up bug where the worker froze under pressure and
never resumed when it cleared.
"""

import fnmatch
import json

import pytest
from isardvdi_common.lib import governed_worker as gw
from rq.exceptions import DequeueTimeout

# --- is_heavy_queue: pure name predicate (heavy tiers only) ------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        # heavy (max-heavy-capped) tiers: template / maintenance (flat + per-cat)
        ("storage.pool-a.maintenance", True),
        ("storage.pool-a.template", True),
        ("storage.pool-a.catA.maintenance", True),
        # reclaim is deferrable but NOT heavy-capped (trivial delete/move_delete)
        ("storage.pool-a.reclaim", False),
        ("storage.pool-a.catA.reclaim", False),
        # governed-but-not-heavy throughput lane
        ("storage.pool-a.bulk", False),
        ("storage.pool-a.catA.bulk", False),
        # background is deferrable but NOT heavy (trivial idle metadata refresh)
        ("storage.pool-a.background", False),
        ("storage.pool-a.catA.background", False),
        # foreground lanes are never heavy
        ("storage.pool-a.interactive", False),
        ("storage.pool-a.standard", False),
        # non-storage / malformed
        ("maintenance", False),  # no storage. prefix -> not a real lane
        ("storage.pool-a.maintenanceish", False),  # tier must match exactly
        (None, False),
        (123, False),
    ],
)
def test_is_heavy_queue(name, expected):
    assert gw.is_heavy_queue(name) is expected


# --- is_deferrable_queue: PSI-defer set (superset of heavy; includes reclaim) ---


@pytest.mark.parametrize(
    "name,expected",
    [
        # deferrable tiers: template / maintenance / reclaim (flat + per-category)
        ("storage.pool-a.template", True),
        ("storage.pool-a.maintenance", True),
        ("storage.pool-a.reclaim", True),
        ("storage.pool-a.catA.reclaim", True),
        ("storage.pool-a.catA.maintenance", True),
        # governed-but-not-deferrable throughput lane
        ("storage.pool-a.bulk", False),
        ("storage.pool-a.catA.bulk", False),
        # background defers (idle-only lifecycle metadata refresh)
        ("storage.pool-a.background", True),
        ("storage.pool-a.catA.background", True),
        # foreground lanes never defer
        ("storage.pool-a.interactive", False),
        ("storage.pool-a.standard", False),
        # non-storage / malformed
        ("reclaim", False),
        (None, False),
    ],
)
def test_is_deferrable_queue(name, expected):
    assert gw.is_deferrable_queue(name) is expected


# --- fakes -------------------------------------------------------------------


class _FakeRedis:
    """In-memory multi-key SET store plus a STRING store (for ``governor:config``)
    and an eval() that emulates both the single-key heavy reserve Lua and the
    dual-key fair reserve Lua. A seed ``members`` set maps to
    ``HEAVY_RUNNING_KEY`` for the heavy-cap tests."""

    def __init__(self, members=None):
        self._sets = {}
        self._kv = {}
        self._lists = {}  # rq:queue:<name> job lists (for lane GC)
        self._zsets = {}  # rq:wip / rq:deferred / rq:scheduled registries
        self._hashes = {}
        self._expires = {}
        if members:
            self._sets[gw.HEAVY_RUNNING_KEY] = set(members)

    def _s(self, key):
        return self._sets.setdefault(key, set())

    def scan_iter(self, match=None, count=None):
        # Cursor-less stand-in: yield every key across all stores matching.
        allkeys = (
            list(self._sets) + list(self._kv) + list(self._lists) + list(self._zsets)
        )
        for k in allkeys:
            if match is None or fnmatch.fnmatch(k, match):
                yield k

    def llen(self, key):
        return len(self._lists.get(key, ()))

    def zcard(self, key):
        return len(self._zsets.get(key, ()))

    def rpush(self, key, *vals):
        self._lists.setdefault(key, []).extend(vals)
        return len(self._lists[key])

    def zadd(self, key, mapping):
        self._zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zrange(self, key, start, end):
        members = [
            m for m, _ in sorted(self._zsets.get(key, {}).items(), key=lambda kv: kv[1])
        ]
        return members[start:] if end == -1 else members[start : end + 1]

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, ex=None):
        self._kv[key] = value
        return True

    def exists(self, *keys):
        n = 0
        for k in keys:
            if k in self._kv or k in self._sets or k in self._lists or k in self._zsets:
                n += 1
        return n

    def scard(self, key):
        return len(self._sets.get(key, ()))

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

    def expire(self, key, ttl):
        self._expires[key] = ttl
        return True

    def hset(self, key, mapping=None):
        h = self._hashes.setdefault(key, {})
        if mapping:
            h.update({k: str(v) for k, v in mapping.items()})
        return len(mapping or {})

    def hgetall(self, key):
        return dict(self._hashes.get(key, {}))

    def pipeline(self):
        return _FakePipeline(self)

    def keys(self, pattern):
        return [k for k in self._sets if fnmatch.fnmatch(k, pattern)]

    def delete(self, *keys):
        n = 0
        for k in keys:
            for store in (self._sets, self._kv, self._lists, self._zsets):
                if k in store:
                    del store[k]
                    n += 1
        return n

    def eval(self, script, numkeys, *args):
        if int(numkeys) == 5:  # lane GC: rq:queues, rq:queue, wip, deferred, sched
            queues_key, qkey, wip, deferred, sched = (
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
            )
            member = args[5]
            if (
                self.llen(qkey) == 0
                and self.zcard(wip) == 0
                and self.zcard(deferred) == 0
                and self.zcard(sched) == 0
            ):
                return self.srem(queues_key, member)
            return 0
        if int(numkeys) == 1 and len(args) == 1:  # empty-set GC: SCARD==0 -> DEL
            (key,) = args
            if len(self._sets.get(key, ())) == 0:
                return self.delete(key)
            return 0
        if int(numkeys) == 1:  # single-key heavy reserve
            key, job_id, max_heavy, _ttl = args
            s = self._s(key)
            if len(s) < int(max_heavy):
                s.add(job_id)
                return 1
            return 0
        # dual-key fair reserve: cat_key, global_key, job_id, cap, isbg, maxh, ttl
        cat_key, global_key = args[0], args[1]
        job_id, cap, isbg, maxh = args[2], int(args[3]), int(args[4]), int(args[5])
        cs, gs = self._s(cat_key), self._s(global_key)
        if cap >= 0 and len(cs) >= cap:
            return 0
        if isbg == 1 and len(gs) >= maxh:
            return 0
        cs.add(job_id)
        if isbg == 1:
            gs.add(job_id)
        return 1


class _FakePipeline:
    """Minimal pipeline supporting the exact ops ``_publish_status`` issues
    (``hset(mapping=)`` + ``expire``), applied on ``execute``."""

    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def hset(self, key, mapping=None):
        self._ops.append(("hset", key, mapping))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    def execute(self):
        out = []
        for op in self._ops:
            if op[0] == "hset":
                out.append(self._redis.hset(op[1], mapping=op[2]))
            else:
                out.append(self._redis.expire(op[1], op[2]))
        self._ops = []
        return out


class _Q:
    def __init__(self, name):
        self.name = name
        self.pushed = None

    def push_job_id(self, job_id, at_front=False):
        self.pushed = (job_id, at_front)


class _Job:
    def __init__(self, jid, status="started"):
        self.id = jid
        self._status = status
        self.redis_server_version = None

    def get_status(self, refresh=False):
        return self._status


class _JobClass:
    """Stands in for ``self.job_class``; fetch() looks up a status table."""

    table = {}

    @classmethod
    def fetch(cls, jid, connection=None):
        if jid not in cls.table:
            raise KeyError(jid)
        return _Job(jid, cls.table[jid])


class _FakeQueueClass:
    """Stands in for ``self.queue_class``; ``dequeue_any`` records the queue set
    it was called with and returns scripted results. Script entries:
      ``(job, queue)`` -> returned; ``"timeout"`` -> raises DequeueTimeout;
      ``"none"`` -> returns None (burst/non-blocking drain). Exhausted -> timeout.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []  # list of [queue names] per dequeue_any call

    def dequeue_any(
        self,
        queues,
        timeout,
        connection=None,
        job_class=None,
        serializer=None,
        death_penalty_class=None,
    ):
        self.calls.append([q.name for q in queues])
        if not self.script:
            raise DequeueTimeout(timeout, [])
        item = self.script.pop(0)
        if item == "timeout":
            raise DequeueTimeout(timeout, [])
        if item == "none":
            return None
        return item


class _TestWorker(gw.GovernedWorker):
    # ``should_run_maintenance_tasks`` is a read-only property on the RQ Worker;
    # shadow it with a plain class attribute so the dequeue loop never triggers
    # maintenance in these unit tests.
    should_run_maintenance_tasks = False


def _worker(
    connection,
    cpu_path="x",
    io_path="x",
    psi_limit=40.0,
    max_heavy=2,
    queue_class=None,
    mem_path="x",
):
    w = object.__new__(_TestWorker)  # skip Worker.__init__ (needs a queue)
    # env/hardcoded fallbacks (Worker.__init__ is skipped). _refresh_live_config
    # reads the ``governor:config`` Redis key (absent here unless a test sets it)
    # and merges it over these env defaults each poll — never touching rdb.
    w._env_enabled = True
    w._env_psi_limit = psi_limit
    w._env_max_heavy = max_heavy
    w._env_backoff = 1
    w._env_category_default_max_inflight = None
    w.gov_enabled = True
    w.gov_psi_limit = psi_limit
    w.gov_max_heavy = max_heavy
    w.gov_backoff = 1
    w.gov_category_weights = {}
    w.gov_category_max_inflight = {}
    w.gov_category_default_max_inflight = None
    w._wrr_cursor = 0
    # Observability state (GovernedWorker.__init__ sets these; the builder skips
    # __init__, so mirror them or the per-poll status publish would AttributeError).
    w.name = "test-worker"
    w._last_job_id = None
    w._last_job_action = None
    # Phase-2 multitenancy is a structural env switch; default OFF (P1 flat path)
    # in tests unless a test flips it. _floor = ungoverned bg-floor mode.
    w.multitenancy = False
    w._floor = False
    w._fair_targets = set()
    w._fair_queue_cache = {}
    w.gov_cpu_psi_path = cpu_path
    w.gov_io_psi_path = io_path
    w.gov_mem_psi_path = mem_path
    w.connection = connection
    w.job_class = _JobClass
    w.serializer = None
    w.death_penalty_class = None
    w.queue_class = queue_class
    # Stub the RQ Worker plumbing the dequeue loop touches (state/heartbeat/etc).
    w.heartbeat = lambda *a, **k: None
    w.set_state = lambda *a, **k: None
    w.procline = lambda *a, **k: None
    w.reorder_queues = lambda *a, **k: None
    w.run_maintenance_tasks = lambda: None
    w.get_redis_server_version = lambda: (7, 0, 0)
    w.queue_names = lambda: [q.name for q in getattr(w, "_ordered_queues", [])]
    return w


def _psi_file(tmp_path, name, value):
    p = tmp_path / name
    p.write_text(f"some avg10={value} avg60=0 avg300=0 total=0\n")
    return str(p)


# --- PSI signal --------------------------------------------------------------


def test_pressure_high_true_when_cpu_over_limit(tmp_path):
    w = _worker(
        _FakeRedis(), _psi_file(tmp_path, "cpu", 99.0), _psi_file(tmp_path, "io", 1.0)
    )
    assert w._pressure_high() is True


def test_pressure_high_true_when_io_over_limit(tmp_path):
    w = _worker(
        _FakeRedis(), _psi_file(tmp_path, "cpu", 1.0), _psi_file(tmp_path, "io", 88.0)
    )
    assert w._pressure_high() is True


def test_pressure_high_false_when_both_below_limit(tmp_path):
    w = _worker(
        _FakeRedis(), _psi_file(tmp_path, "cpu", 10.0), _psi_file(tmp_path, "io", 20.0)
    )
    assert w._pressure_high() is False


def test_pressure_high_missing_file_is_no_pressure(tmp_path):
    w = _worker(_FakeRedis(), str(tmp_path / "absent-cpu"), str(tmp_path / "absent-io"))
    assert w._pressure_high() is False


def test_pressure_high_true_when_mem_over_limit(tmp_path):
    # Memory PSI alone (cpu/io calm) must trip deferral — the third dimension.
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 2.0),
        mem_path=_psi_file(tmp_path, "mem", 90.0),
    )
    assert w._pressure_high() is True


def test_pressure_high_false_when_mem_below_limit(tmp_path):
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 2.0),
        mem_path=_psi_file(tmp_path, "mem", 5.0),
    )
    assert w._pressure_high() is False


def test_pressure_high_missing_mem_file_is_no_pressure(tmp_path):
    # A kernel without /proc/pressure/memory -> read_pressure 0.0 -> no mem defer.
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 2.0),
        mem_path=str(tmp_path / "absent-mem"),
    )
    assert w._pressure_high() is False


# --- heavy cap (SCARD) -------------------------------------------------------


def test_heavy_at_cap_true_at_and_above():
    assert _worker(_FakeRedis({"a", "b"}), max_heavy=2)._heavy_at_cap() is True
    assert _worker(_FakeRedis({"a", "b", "c"}), max_heavy=2)._heavy_at_cap() is True


def test_heavy_at_cap_false_below():
    assert _worker(_FakeRedis({"a"}), max_heavy=2)._heavy_at_cap() is False
    assert _worker(_FakeRedis(), max_heavy=2)._heavy_at_cap() is False


def test_heavy_at_cap_survives_redis_error():
    class _Boom:
        def scard(self, key):
            raise RuntimeError("redis down")

    assert _worker(_Boom())._heavy_at_cap() is False


# --- atomic reserve / release ------------------------------------------------


def test_reserve_heavy_admits_under_cap_and_denies_at_cap():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    assert w._reserve_heavy("j1") is True
    assert w._reserve_heavy("j2") is True
    assert w._reserve_heavy("j3") is False  # at cap
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 2


def test_release_heavy_frees_a_slot():
    r = _FakeRedis({"j1", "j2"})
    w = _worker(r, max_heavy=2)
    w._release_heavy("j1")
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1
    assert w._reserve_heavy("j3") is True


def test_reserve_heavy_fails_open_on_redis_error():
    class _Boom:
        def eval(self, *a):
            raise RuntimeError("redis down")

    # a redis hiccup must not wedge the worker -> admit rather than block forever
    assert _worker(_Boom())._reserve_heavy("j1") is True


# --- reconcile: prune leaked ids (dead-worker self-heal) ---------------------


def test_reconcile_prunes_finished_and_missing_but_keeps_running():
    r = _FakeRedis({"running", "done", "gone"})
    _JobClass.table = {"running": "started", "done": "finished"}  # 'gone' -> KeyError
    w = _worker(r, max_heavy=2)
    w._reconcile_heavy()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"running"}


# --- worker-liveness self-heal: reclaim slots of dead workers (#4a / #4b) -----


def test_reconcile_prunes_started_job_of_dead_worker():
    # #4a: an OOM/SIGKILL'd worker leaves its job status "started" forever; the
    # status check keeps it, but the reserving worker is gone -> reclaim the slot.
    r = _FakeRedis({"j1"})
    _JobClass.table = {"j1": "started"}
    r.set(gw.reserved_by_key("j1"), "deadworker")  # owner recorded, worker absent
    w = _worker(r, max_heavy=2)
    w._reconcile_heavy()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == set()
    assert r.get(gw.reserved_by_key("j1")) is None  # owner tag cleaned up too


def test_reconcile_prunes_queued_reservation_of_dead_worker():
    # #4b: a SIGTERM between _admit's reservation and execute_job leaves the job
    # "queued" (a live status) forever. Worker-liveness reclaims it.
    r = _FakeRedis({"j2"})
    _JobClass.table = {"j2": "queued"}
    r.set(gw.reserved_by_key("j2"), "deadworker")
    w = _worker(r, max_heavy=2)
    w._reconcile_heavy()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == set()


def test_reconcile_keeps_started_job_of_live_worker():
    r = _FakeRedis({"j3"})
    _JobClass.table = {"j3": "started"}
    r.set(gw.reserved_by_key("j3"), "liveworker")
    r.set("rq:worker:liveworker", "1")  # heartbeat key present -> worker alive
    w = _worker(r, max_heavy=2)
    w._reconcile_heavy()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"j3"}


def test_reconcile_keeps_reservation_without_owner_tag():
    # Fail-open (backward compat): a reservation with no owner tag (pre-upgrade,
    # or the tiny window before the tag lands) must NOT be pruned -> never
    # over-admit under a live job.
    r = _FakeRedis({"j4"})
    _JobClass.table = {"j4": "started"}  # no reserved_by tag
    w = _worker(r, max_heavy=2)
    w._reconcile_heavy()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"j4"}


def test_reserve_heavy_records_owner_and_release_clears_it():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    w.name = "test-worker"  # RQ sets this in __init__; the builder skips it
    assert w._reserve_heavy("j1") is True
    assert r.get(gw.reserved_by_key("j1")) == "test-worker"
    w._release_heavy("j1")
    assert r.get(gw.reserved_by_key("j1")) is None
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0


def test_reserve_fair_records_owner_and_release_clears_it():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    w.name = "test-worker"
    w.gov_category_max_inflight = {"catA": 5}
    assert w._reserve_fair("j9", "POOL", "catA", is_heavy=True) is True
    assert r.get(gw.reserved_by_key("j9")) == "test-worker"
    w._release_fair("j9", "POOL", "catA", is_heavy=True)
    assert r.get(gw.reserved_by_key("j9")) is None


# --- kill-switch re-enable seeds counters from live registries -----------


def test_seed_running_populates_heavy_from_wip():
    r = _FakeRedis()
    r.zadd("rq:wip:storage.P.maintenance", {"j1": 0, "j2": 0})  # ran while off
    w = _worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._seed_running_from_registries()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"j1", "j2"}


def test_seed_running_skips_bulk_for_heavy_counter():
    r = _FakeRedis()
    r.zadd("rq:wip:storage.P.bulk", {"jb": 0})  # bulk is fair but NOT heavy
    w = _worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.bulk"])
    w._seed_running_from_registries()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == set()


def test_seed_running_multitenancy_seeds_category_and_heavy():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.zadd("rq:wip:storage.P.catA.maintenance", {"j3": 0})
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    w._seed_running_from_registries()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"j3"}
    assert r.smembers(gw.category_running_key("P", "catA")) == {"j3"}


def test_refresh_seeds_heavy_on_disabled_to_enabled_transition():
    r = _FakeRedis()
    r.zadd("rq:wip:storage.P.maintenance", {"j1": 0})  # uncounted while off
    r.set(gw.GOVERNOR_CONFIG_KEY, json.dumps({"enabled": True}))
    w = _worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w.gov_enabled = False  # governor was OFF
    w._refresh_live_config()  # config flips it ON -> seed before enforcing
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == {"j1"}


def test_refresh_does_not_seed_when_already_enabled():
    # No transition -> must NOT seed every poll (that would keep re-adding).
    r = _FakeRedis()
    r.zadd("rq:wip:storage.P.maintenance", {"j1": 0})
    r.set(gw.GOVERNOR_CONFIG_KEY, json.dumps({"enabled": True}))
    w = _worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w.gov_enabled = True  # already ON
    w._refresh_live_config()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == set()


def test_floor_never_seeds_on_reenable():
    r = _FakeRedis()
    r.zadd("rq:wip:storage.P.maintenance", {"j1": 0})
    r.set(gw.GOVERNOR_CONFIG_KEY, json.dumps({"enabled": True}))
    w = _worker(r)
    w._floor = True  # ungoverned floor never reserves, so never seeds
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w.gov_enabled = False
    w._refresh_live_config()
    assert r.smembers(gw.HEAVY_RUNNING_KEY) == set()


# --- dequeue path: PSI / cap gating on the REAL queue set --------------------
#
# These assert on the queue list passed to dequeue_any (exactly what RQ BLPOPs)
# and on actual admission — not on a decoupled counter or a monkeypatched super.


def test_dequeue_defers_maintenance_under_pressure(tmp_path):
    # THE P1-A regression: under high PSI the maintenance queue must be absent
    # from the set the worker actually reads.
    bg, inter = _Q("storage.p.maintenance"), _Q("storage.p.interactive")
    qc = _FakeQueueClass([(_Job("i1"), inter)])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 99.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [bg, inter]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert queue is inter
    # maintenance excluded; the collapsed single-queue set is duplicated (review
    # #1) so RQ never takes the reliable/intermediate path.
    assert "storage.p.maintenance" not in qc.calls[0]
    assert "storage.p.interactive" in qc.calls[0]


def test_dequeue_defers_maintenance_at_cap(tmp_path):
    qc = _FakeQueueClass([(_Job("i1"), _Q("storage.p.interactive"))])
    w = _worker(
        _FakeRedis({"a", "b"}),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        max_heavy=2,
        queue_class=qc,
    )
    _JobClass.table = {"a": "started", "b": "started"}  # nothing to reconcile away
    bg, inter = _Q("storage.p.maintenance"), _Q("storage.p.interactive")
    w._ordered_queues = [bg, inter]
    w.dequeue_job_and_maintain_ttl(10)
    assert "storage.p.maintenance" not in qc.calls[0]


def test_dequeue_single_queue_duplicated_to_dodge_intermediate_leak(tmp_path):
    # When the per-poll filtered set collapses to
    # ONE queue while the static set is larger, RQ's reliable-queue path would
    # BLMOVE the job into <queue>:intermediate and never remove it (removal keys
    # off len(self.queues)!=1), later flipping a SUCCEEDED job to failed. The
    # dequeue must force RQ's multi-queue branch by duplicating the sole queue.
    tmpl = _Q("storage.p.template")
    bulk = _Q("storage.p.bulk")
    maint = _Q("storage.p.maintenance")
    recl = _Q("storage.p.reclaim")
    qc = _FakeQueueClass([(_Job("b1"), bulk)])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 99.0),  # high PSI -> heavy tiers deferred
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [tmpl, bulk, maint, recl]  # template-lane static set (4)
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert queue is bulk
    # filtered set was [bulk] (three heavy tiers deferred) -> duplicated so RQ
    # takes the non-reliable multi-queue branch and never touches :intermediate.
    assert qc.calls[0] == ["storage.p.bulk", "storage.p.bulk"]


def test_dequeue_single_static_queue_not_duplicated(tmp_path):
    # A genuinely single-queue worker (static set == 1) keeps RQ's reliable mode:
    # len(self.queues)==1 there, so removal already matches — no duplication.
    inter = _Q("storage.p.interactive")
    qc = _FakeQueueClass([(_Job("i1"), inter)])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [inter]
    w.dequeue_job_and_maintain_ttl(10)
    assert qc.calls[0] == ["storage.p.interactive"]  # not duplicated


def test_dequeue_includes_maintenance_when_clear(tmp_path):
    r = _FakeRedis()
    qc = _FakeQueueClass([(_Job("b1"), _Q("storage.p.maintenance"))])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    bg, inter = _Q("storage.p.maintenance"), _Q("storage.p.interactive")
    w._ordered_queues = [bg, inter]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert "storage.p.maintenance" in qc.calls[0]  # not deferred when clear
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1  # and the heavy slot was reserved


def test_dequeue_reserves_slot_for_maintenance_job(tmp_path):
    r = _FakeRedis()
    qc = _FakeQueueClass([(_Job("j1"), _Q("storage.p.maintenance"))])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        max_heavy=2,
        queue_class=qc,
    )
    bg = _Q("storage.p.maintenance")
    w._ordered_queues = [bg]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("j1", "storage.p.maintenance")
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1


def test_dequeue_pushes_back_at_front_when_reserve_denied(tmp_path):
    # maintenance job slips through (top check raced) but the atomic reserve
    # denies it -> it must go back at the FRONT and the worker steps aside,
    # then pick up the next (foreground) job instead.
    r = _FakeRedis()
    bg = _Q("storage.p.maintenance")
    inter = _Q("storage.p.interactive")
    qc = _FakeQueueClass([(_Job("j1"), bg), (_Job("i1"), inter)])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [bg, inter]
    w._reserve_heavy = lambda job_id: False  # force the lost-race denial
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert bg.pushed == ("j1", True)  # re-enqueued at front
    assert (job.id, queue.name) == ("i1", "storage.p.interactive")


# --- the follow-up regression: never freeze, always resume -------------------


def test_dequeue_never_returns_none_while_blocking(tmp_path):
    # RQ's work() quits the worker on a None return. Under repeated BLPOP
    # timeouts (no work yet) the governor must keep polling and eventually
    # return the job that arrives — never None.
    inter = _Q("storage.p.interactive")
    qc = _FakeQueueClass(["timeout", "timeout", (_Job("i1"), inter)])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [inter]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("i1", "storage.p.interactive")
    assert len(qc.calls) == 3  # kept polling across both timeouts


def test_dequeue_resumes_maintenance_after_pressure_clears(tmp_path):
    # THE staging LOW-phase bug: once PSI drops, the worker must start reading
    # maintenance again within a poll and admit the heavy job — not stay frozen
    # on the filtered (non-maintenance) set.
    r = _FakeRedis()
    bg, inter = _Q("storage.p.maintenance"), _Q("storage.p.interactive")
    qc = _FakeQueueClass(["timeout", "timeout", (_Job("b1"), bg)])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [bg, inter]
    pressure_states = [True, True, False]  # high, high, then clears
    w._pressure_high = lambda: pressure_states.pop(0) if pressure_states else False
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("b1", "storage.p.maintenance")
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1  # admitted once clear
    # first two polls excluded maintenance (single-queue set duplicated),
    # the third (cleared) included it as a genuine 2-queue set.
    assert "storage.p.maintenance" not in qc.calls[0]
    assert "storage.p.maintenance" not in qc.calls[1]
    assert qc.calls[2] == ["storage.p.maintenance", "storage.p.interactive"]


def test_dequeue_burst_drains_to_none(tmp_path):
    # In --burst (timeout=None) an empty drain returns None so the worker quits;
    # we must not loop forever there.
    qc = _FakeQueueClass(["none"])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [_Q("storage.p.interactive")]
    assert w.dequeue_job_and_maintain_ttl(None) is None


# --- live config: DB->env->hardcoded merge + kill-switch ---------------------

_ENV = {
    "enabled": True,
    "psi_limit": 40.0,
    "max_heavy": 2,
    "backoff": 3,
    "category_default_max_inflight": None,
}


def _knobs(eff):
    return {k: eff[k] for k in ("enabled", "psi_limit", "max_heavy", "backoff")}


def test_merge_live_config_prefers_db_over_env():
    eff = gw._merge_live_config(
        {"enabled": False, "psi_limit": 55, "max_heavy": 4, "backoff": 1}, _ENV
    )
    assert _knobs(eff) == {
        "enabled": False,
        "psi_limit": 55.0,
        "max_heavy": 4,
        "backoff": 1,
    }


def test_merge_live_config_falls_back_per_key_on_missing_or_bad():
    # missing keys, a non-numeric psi_limit, and an out-of-range (0) max_heavy
    # each fall back independently — one bad value never disables the governor.
    eff = gw._merge_live_config({"psi_limit": "oops", "max_heavy": 0}, _ENV)
    assert _knobs(eff) == {
        "enabled": True,
        "psi_limit": 40.0,
        "max_heavy": 2,
        "backoff": 3,
    }


def test_merge_live_config_empty_block_is_all_env():
    expected = {"enabled": True, "psi_limit": 40.0, "max_heavy": 2, "backoff": 3}
    assert _knobs(gw._merge_live_config({}, _ENV)) == expected
    assert _knobs(gw._merge_live_config(None, _ENV)) == expected


# --- live config delivered via the governor:config Redis mirror (NOT rdb) ----
#
# apiv4 mirrors config[1].storage_scheduler into the shared RQ Redis; the worker
# reads that key and NEVER opens a RethinkDB connection (isard-storage may live
# on a different host from isard-db).


def test_refresh_live_config_reads_redis_mirror():
    r = _FakeRedis()
    r.set(
        gw.GOVERNOR_CONFIG_KEY,
        json.dumps({"enabled": False, "psi_limit": 12, "max_heavy": 5, "backoff": 2}),
    )
    w = _worker(r)
    w._refresh_live_config()
    assert w.gov_enabled is False
    assert w.gov_psi_limit == 12.0
    assert w.gov_max_heavy == 5
    assert w.gov_backoff == 2


def test_refresh_live_config_absent_key_is_all_env():
    w = _worker(_FakeRedis())  # no governor:config published
    w.gov_max_heavy = 99  # clobber to prove the refresh re-derives from env
    w._refresh_live_config()
    assert w.gov_enabled is True
    assert w.gov_psi_limit == 40.0
    assert w.gov_max_heavy == 2  # _env_max_heavy default
    assert w.gov_backoff == 1  # _env_backoff set by _worker()


def test_refresh_live_config_bad_json_falls_back_to_env():
    r = _FakeRedis()
    r.set(gw.GOVERNOR_CONFIG_KEY, "{not valid json")
    w = _worker(r)
    w._refresh_live_config()
    assert w.gov_enabled is True
    assert w.gov_max_heavy == 2


def test_refresh_live_config_non_dict_json_falls_back_to_env():
    r = _FakeRedis()
    r.set(gw.GOVERNOR_CONFIG_KEY, json.dumps([1, 2, 3]))  # valid JSON, not an object
    w = _worker(r)
    w._refresh_live_config()
    assert w.gov_max_heavy == 2


def test_refresh_live_config_survives_redis_get_error():
    class _Boom:
        def get(self, key):
            raise RuntimeError("redis down")

    w = _worker(_Boom())
    w._refresh_live_config()  # must not raise
    assert w.gov_max_heavy == 2  # fell back to env


def test_dequeue_picks_up_redis_kill_switch_live(tmp_path):
    # End-to-end via the dequeue loop: publishing enabled=false to governor:config
    # disables gating within one poll (no restart) — maintenance runs even under
    # high PSI / at cap, and no heavy slot is reserved. Proves the live pickup
    # path is the Redis mirror, not rdb.
    r = _FakeRedis({"a", "b"})  # heavy set already at cap
    r.set(gw.GOVERNOR_CONFIG_KEY, json.dumps({"enabled": False}))
    bg = _Q("storage.p.maintenance")
    qc = _FakeQueueClass([(_Job("b1"), bg)])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 99.0),
        _psi_file(tmp_path, "io", 99.0),
        max_heavy=2,
        queue_class=qc,
    )
    w._ordered_queues = [bg]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("b1", "storage.p.maintenance")
    assert qc.calls[0] == ["storage.p.maintenance"]  # not filtered despite pressure
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 2  # unchanged: no reserve when disabled


def test_kill_switch_disables_deferral(tmp_path):
    # governor disabled -> never defers even under high PSI / at cap, and takes
    # maintenance ungoverned (no reserve).
    r = _FakeRedis({"a", "b"})  # at cap
    bg = _Q("storage.p.maintenance")
    qc = _FakeQueueClass([(_Job("b1"), bg)])
    w = _worker(
        r,
        _psi_file(tmp_path, "cpu", 99.0),  # high pressure
        _psi_file(tmp_path, "io", 99.0),
        max_heavy=2,
        queue_class=qc,
    )
    w._env_enabled = False  # kill-switch off; _refresh_live_config picks it up
    w._ordered_queues = [bg]
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("b1", "storage.p.maintenance")
    assert qc.calls[0] == ["storage.p.maintenance"]  # not filtered out
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 2  # unchanged: no reserve when off


def test_dequeue_honors_max_idle_time_budget(tmp_path):
    # With a max_idle_time budget and only timeouts, the worker eventually
    # returns None (idle quit) instead of polling forever.
    qc = _FakeQueueClass(["timeout", "timeout", "timeout"])
    w = _worker(
        _FakeRedis(),
        _psi_file(tmp_path, "cpu", 1.0),
        _psi_file(tmp_path, "io", 1.0),
        queue_class=qc,
    )
    w._ordered_queues = [_Q("storage.p.interactive")]
    # a zero budget expires on the first timeout check
    assert w.dequeue_job_and_maintain_ttl(10, max_idle_time=0) is None


# --- Phase-2 per-category counter layer + config merge -----------------------


def test_merge_live_config_includes_fairness_tuning_keys():
    # The on/off is the STORAGE_QUEUE_MULTITENANCY env switch (not merged here);
    # only the per-category TUNING knobs are live-merged.
    env = {
        "enabled": True,
        "psi_limit": 40.0,
        "max_heavy": 2,
        "backoff": 3,
        "category_default_max_inflight": None,
    }
    eff = gw._merge_live_config(
        {
            "category_weights": {"catA": 3, "bad": "x", "catB": 0},
            "category_max_inflight": {"catA": 2},
            "category_default_max_inflight": 5,
        },
        env,
    )
    assert "fair_scheduling" not in eff  # replaced by the env switch
    assert eff["category_weights"] == {"catA": 3}  # bad/0 dropped
    assert eff["category_max_inflight"] == {"catA": 2}
    assert eff["category_default_max_inflight"] == 5


def test_merge_live_config_fairness_tuning_defaults_off():
    env = {
        "enabled": True,
        "psi_limit": 40.0,
        "max_heavy": 2,
        "backoff": 3,
        "category_default_max_inflight": None,
    }
    eff = gw._merge_live_config({}, env)
    assert eff["category_weights"] == {}
    assert eff["category_max_inflight"] == {}
    assert eff["category_default_max_inflight"] is None


def test_category_cap_explicit_over_default_over_none():
    w = _worker(_FakeRedis())
    w.gov_category_max_inflight = {"catA": 4}
    w.gov_category_default_max_inflight = 2
    assert w._category_cap("catA") == 4  # explicit
    assert w._category_cap("catB") == 2  # default
    w.gov_category_default_max_inflight = None
    assert w._category_cap("catB") is None  # uncapped


def test_reserve_fair_bulk_counts_category_and_caps_it():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    w.gov_category_max_inflight = {"catA": 2}
    assert w._reserve_fair("j1", "POOL", "catA", is_heavy=False) is True
    assert w._reserve_fair("j2", "POOL", "catA", is_heavy=False) is True
    assert w._reserve_fair("j3", "POOL", "catA", is_heavy=False) is False  # at cap
    assert r.scard(gw.category_running_key("POOL", "catA")) == 2
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0  # bulk never touches the heavy set


def test_reserve_fair_maintenance_reserves_both_slots():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    w.gov_category_default_max_inflight = None  # uncapped category
    assert w._reserve_fair("j1", "POOL", "catA", is_heavy=True) is True
    assert r.scard(gw.category_running_key("POOL", "catA")) == 1
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1


def test_reserve_fair_atomic_denies_without_partial_when_global_full():
    r = _FakeRedis({"x", "y"})  # global heavy already at cap (max_heavy=2)
    w = _worker(r, max_heavy=2)
    w.gov_category_default_max_inflight = None
    assert w._reserve_fair("j1", "POOL", "catA", is_heavy=True) is False
    # denial must NOT have incremented the per-category set (no partial reserve)
    assert r.scard(gw.category_running_key("POOL", "catA")) == 0


def test_reserve_fair_uncapped_counts_but_never_denies():
    r = _FakeRedis()
    w = _worker(r)
    w.gov_category_default_max_inflight = None
    for i in range(5):
        assert w._reserve_fair(f"j{i}", "POOL", "catA", is_heavy=False) is True
    assert r.scard(gw.category_running_key("POOL", "catA")) == 5


def test_release_fair_frees_both_slots():
    r = _FakeRedis()
    w = _worker(r, max_heavy=2)
    w.gov_category_default_max_inflight = None
    w._reserve_fair("j1", "POOL", "catA", is_heavy=True)
    w._release_fair("j1", "POOL", "catA", is_heavy=True)
    assert r.scard(gw.category_running_key("POOL", "catA")) == 0
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0


def test_reconcile_categories_prunes_stale_and_deletes_empty():
    r = _FakeRedis()
    r.sadd(gw.category_running_key("POOL", "catA"), "running", "gone")
    r.sadd(gw.category_running_key("POOL", "catB"), "dead")
    _JobClass.table = {"running": "started"}  # gone/dead -> not live
    w = _worker(r)
    w._reconcile_categories()
    assert r.smembers(gw.category_running_key("POOL", "catA")) == {"running"}
    # catB drained to empty -> the key is deleted so discovery won't scan it
    assert gw.category_running_key("POOL", "catB") not in r.keys("governor:running:*")
    # catA still has a live member -> its key must survive (the GC deletes ONLY an
    # empty set, atomically — a scard==0/delete pair would race a live reserve).
    assert gw.category_running_key("POOL", "catA") in r.keys("governor:running:*")


def test_reconcile_categories_never_deletes_nonempty_set():
    # The empty-set GC must be a no-op on any set that still holds a live member,
    # so a concurrent reservation can't be wiped (adversarial TOCTOU finding).
    r = _FakeRedis()
    r.sadd(gw.category_running_key("POOL", "catA"), "live")
    _JobClass.table = {"live": "started"}
    w = _worker(r)
    w._reconcile_categories()
    assert r.smembers(gw.category_running_key("POOL", "catA")) == {"live"}


def test_reconcile_categories_scans_never_keys(monkeypatch):
    # The reconcile must enumerate via SCAN, never the O(N) KEYS
    # (which blocks the single-threaded shared broker).
    r = _FakeRedis()
    r.sadd(gw.category_running_key("POOL", "catA"), "gone")  # stale -> pruned
    _JobClass.table = {}

    def _boom(*a, **k):
        raise AssertionError("KEYS must not be used on the shared broker (#13)")

    monkeypatch.setattr(r, "keys", _boom)
    w = _worker(r)
    w._reconcile_categories()  # goes through SCAN; never touches KEYS
    assert r.scard(gw.category_running_key("POOL", "catA")) == 0


# --- registry-aware GC of drained per-category lanes from rq:queues ------


def test_gc_removes_fully_drained_category_lane():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.bulk")  # empty list + registries
    w = _worker(r)
    w._fair_targets = {("P", "bulk")}
    w._reconcile_categories()
    assert "rq:queue:storage.P.catA.bulk" not in r.smembers("rq:queues")


def test_gc_keeps_lane_with_started_registry_job():
    # registry-aware (the #5 coupling): a lane still holding a StartedJobRegistry
    # job must stay in rq:queues so clean_registries can still rescue it.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.bulk")
    r.zadd("rq:wip:storage.P.catA.bulk", {"job1": 0})
    w = _worker(r)
    w._fair_targets = {("P", "bulk")}
    w._reconcile_categories()
    assert "rq:queue:storage.P.catA.bulk" in r.smembers("rq:queues")


def test_gc_keeps_lane_with_queued_or_deferred_job():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.bulk")
    r.rpush("rq:queue:storage.P.catA.bulk", "job1")  # a queued job
    r.sadd("rq:queues", "rq:queue:storage.P.catB.bulk")
    r.zadd("rq:deferred:storage.P.catB.bulk", {"job2": 0})  # a deferred job
    w = _worker(r)
    w._fair_targets = {("P", "bulk")}
    w._reconcile_categories()
    survivors = r.smembers("rq:queues")
    assert "rq:queue:storage.P.catA.bulk" in survivors
    assert "rq:queue:storage.P.catB.bulk" in survivors


def test_gc_ignores_flat_foreign_and_nonstorage_lanes():
    r = _FakeRedis()
    for n in (
        "rq:queue:storage.P.bulk",  # flat base -> not a per-category lane
        "rq:queue:storage.Q.catA.bulk",  # pool/tier not in _fair_targets
        "rq:queue:core",  # non-storage
    ):
        r.sadd("rq:queues", n)
    w = _worker(r)
    w._fair_targets = {("P", "bulk")}
    w._reconcile_categories()
    assert r.smembers("rq:queues") == {
        "rq:queue:storage.P.bulk",
        "rq:queue:storage.Q.catA.bulk",
        "rq:queue:core",
    }


# ==== Phase-2 WIRING: multitenancy discovery + weighted-RR + fair admit ======
#
# These exercise the LIVE path (discovery -> ordering -> admit -> release), not
# just the counter primitives — the class of coverage whose absence let the
# fairness engine sit inert. Multitenancy is the STORAGE_QUEUE_MULTITENANCY env
# switch (default off); _mt_worker flips it on.


def _mt_worker(r, **kw):
    w = _worker(r, **kw)
    w.multitenancy = True
    return w


class _NameQueue:
    """A minimal Queue stand-in constructible by name (what _make_fair_queue and
    _derive_fair_targets need)."""

    def __init__(self, name, connection=None, job_class=None, serializer=None):
        self.name = name


def _ordered(names):
    return [_NameQueue(n) for n in names]


# --- weighted round-robin ordering (pure) ---


def test_weighted_rotation_empty():
    assert gw.GovernedWorker._weighted_rotation([], {}, 0) == []


def test_weighted_rotation_equal_weight_rotates_lead_by_cursor():
    cats = ["a", "b", "c"]
    leads = [gw.GovernedWorker._weighted_rotation(cats, {}, c)[0] for c in range(3)]
    assert set(leads) == {"a", "b", "c"}  # every cat leads once across 3 polls
    assert (
        sorted(gw.GovernedWorker._weighted_rotation(cats, {}, 0)) == cats
    )  # work-conserving


def test_weighted_rotation_weight_biases_lead_frequency():
    cats = ["a", "b"]
    weights = {"a": 3}  # a -> 3 ring slots, b -> 1: a leads 3/4 of polls
    leads = [
        gw.GovernedWorker._weighted_rotation(cats, weights, c)[0] for c in range(4)
    ]
    assert leads.count("a") == 3 and leads.count("b") == 1


# --- discovery from rq:queues ---


def test_discover_fair_queues_filters_to_targets():
    r = _FakeRedis()
    for n in [
        "rq:queue:storage.P.catA.maintenance",
        "rq:queue:storage.P.catB.maintenance",
        "rq:queue:storage.P.catA.bulk",
        "rq:queue:storage.P.maintenance",  # flat base -> not a category lane
        "rq:queue:storage.Q.catA.maintenance",  # different pool, not a target
        "rq:queue:core",  # non-storage
    ]:
        r.sadd("rq:queues", n)
    w = _mt_worker(r)
    w._fair_targets = {("P", "maintenance"), ("P", "bulk")}
    active = w._discover_fair_queues()
    assert sorted(active[("P", "maintenance")]) == ["catA", "catB"]
    assert active[("P", "bulk")] == ["catA"]
    assert ("Q", "maintenance") not in active


def test_discover_fair_queues_empty_without_targets():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    w = _mt_worker(r)
    w._fair_targets = set()
    assert w._discover_fair_queues() == {}


# --- clean_registries: rescue discovered per-category lanes ------


def test_clean_registries_covers_discovered_category_lanes(monkeypatch):
    # RQ's clean_registries only walks self.queues; the discovered per-category
    # lanes must be added for the maintenance pass so a work-horse OOM on them is
    # rescued, then removed again so self.queues is unchanged for the next dequeue.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd("rq:queues", "rq:queue:storage.P.catB.bulk")
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    base = _ordered(["storage.P.maintenance", "storage.P.bulk"])
    w.queues = list(base)
    w._ordered_queues = base
    w._fair_targets = w._derive_fair_targets()
    seen = {}
    monkeypatch.setattr(
        gw.Worker,
        "clean_registries",
        lambda self: seen.update(q=[x.name for x in self.queues]),
    )
    w.clean_registries()
    # base lanes AND discovered category lanes cleaned in the same pass
    assert "storage.P.catA.maintenance" in seen["q"]
    assert "storage.P.catB.bulk" in seen["q"]
    assert "storage.P.maintenance" in seen["q"] and "storage.P.bulk" in seen["q"]
    # self.queues restored (no category lanes linger -> #1 length logic intact)
    assert [q.name for q in w.queues] == ["storage.P.maintenance", "storage.P.bulk"]


def test_clean_registries_no_extension_without_multitenancy(monkeypatch):
    # Flat (non-multitenancy) worker: no discovery, self.queues never touched.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    w = _worker(r)  # multitenancy off
    base = _ordered(["storage.P.maintenance"])
    w.queues = list(base)
    w._ordered_queues = base
    seen = {}
    monkeypatch.setattr(
        gw.Worker,
        "clean_registries",
        lambda self: seen.update(q=[x.name for x in self.queues]),
    )
    w.clean_registries()
    assert seen["q"] == ["storage.P.maintenance"]
    assert [q.name for q in w.queues] == ["storage.P.maintenance"]


def test_clean_registries_restores_queues_on_super_error(monkeypatch):
    # If RQ's maintenance raises, self.queues must still be restored (finally).
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    base = _ordered(["storage.P.maintenance"])
    w.queues = list(base)
    w._ordered_queues = base
    w._fair_targets = w._derive_fair_targets()

    def _boom(self):
        raise RuntimeError("maintenance blew up")

    monkeypatch.setattr(gw.Worker, "clean_registries", _boom)
    with pytest.raises(RuntimeError):
        w.clean_registries()
    assert [q.name for q in w.queues] == ["storage.P.maintenance"]


# --- fair ordered queues ---


def test_fair_ordered_queues_interleaves_categories_then_base():
    r = _FakeRedis()
    for n in [
        "rq:queue:storage.P.catA.maintenance",
        "rq:queue:storage.P.catB.maintenance",
    ]:
        r.sadd("rq:queues", n)
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance", "storage.P.interactive"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert set(names[:2]) == {
        "storage.P.catA.maintenance",
        "storage.P.catB.maintenance",
    }  # category lanes lead
    assert names[2] == "storage.P.maintenance"  # flat catch-all after them
    assert names[-1] == "storage.P.interactive"  # non-fair lane kept verbatim


def test_fair_ordered_queues_skips_maintenance_when_deferring():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd("rq:queues", "rq:queue:storage.P.catA.bulk")
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(
        ["storage.P.bulk", "storage.P.maintenance", "storage.P.interactive"]
    )
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=True)]
    assert not any("maintenance" in n for n in names)  # heavy tier fully hidden
    assert "storage.P.catA.bulk" in names and "storage.P.bulk" in names  # bulk stays
    assert "storage.P.interactive" in names


def test_fair_ordered_queues_drops_category_at_cap_when_governing():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd("rq:queues", "rq:queue:storage.P.catB.maintenance")
    r.sadd(gw.category_running_key("P", "catA"), "x")  # catA at its cap of 1
    _JobClass.table = {"x": "started"}  # a GENUINE at-cap: the slot's job is live
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {"catA": 1}
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.catA.maintenance" not in names  # at cap -> dropped this poll
    assert "storage.P.catB.maintenance" in names  # under cap -> kept
    assert "storage.P.maintenance" in names  # base catch-all always stays


def test_fair_ordered_queues_floor_ignores_caps():
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd(gw.category_running_key("P", "catA"), "x")
    w = _mt_worker(r)
    w._floor = True  # ungoverned floor never drops at-cap categories
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {"catA": 1}
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.catA.maintenance" in names  # floor serves it despite the cap


def test_category_at_cap_self_heals_leaked_slot():
    # A slot leaked by a dead work-horse must not keep a category
    # at cap forever. _category_at_cap prunes the stale member and re-checks
    # (the runtime analogue of the boot-only _reconcile_categories).
    r = _FakeRedis()
    r.sadd(gw.category_running_key("P", "catA"), "gone")  # job vanished -> stale
    _JobClass.table = {}  # 'gone' not live -> should be pruned on the at-cap check
    w = _mt_worker(r)
    w.gov_category_max_inflight = {"catA": 1}
    assert w._category_at_cap("P", "catA") is False  # leaked slot pruned, not at cap
    assert r.scard(gw.category_running_key("P", "catA")) == 0


def test_category_at_cap_keeps_live_slot():
    # the self-heal must NOT prune a genuinely-running job: a real at-cap holds.
    r = _FakeRedis()
    r.sadd(gw.category_running_key("P", "catA"), "live")
    _JobClass.table = {"live": "started"}
    w = _mt_worker(r)
    w.gov_category_max_inflight = {"catA": 1}
    assert w._category_at_cap("P", "catA") is True
    assert r.smembers(gw.category_running_key("P", "catA")) == {"live"}


def test_fair_ordered_queues_recovers_category_after_leak():
    # end-to-end at the ordering layer: a category whose only slot is a dead job
    # is served again this poll (not stranded until the next worker restart).
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd(gw.category_running_key("P", "catA"), "dead")  # leaked slot
    _JobClass.table = {}  # 'dead' -> KeyError -> stale
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {"catA": 1}
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.catA.maintenance" in names  # recovered, not dropped
    assert r.scard(gw.category_running_key("P", "catA")) == 0  # leaked slot healed


def test_fair_ordered_queues_drops_flat_catchall_when_nocat_at_cap_governing():
    # Regression: the flat catch-all lane's jobs have no category segment, so
    # _admit reserves them against NULL_CATEGORY (_nocat). If that sentinel is at
    # its cap the flat lane must be dropped too — otherwise a queued null-category
    # job is popped, always denied by _reserve_fair, pushed back at front and
    # re-popped: a no-sleep tight-spin (adversarial finding, HIGH).
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd(gw.category_running_key("P", gw.NULL_CATEGORY), "x")  # _nocat at cap 1
    _JobClass.table = {"x": "started"}  # a GENUINE at-cap: the slot's job is live
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {gw.NULL_CATEGORY: 1}
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.maintenance" not in names  # flat catch-all dropped at _nocat cap
    assert "storage.P.catA.maintenance" in names  # under-cap category still served


def test_fair_ordered_queues_keeps_flat_catchall_when_nocat_under_cap():
    # The symmetric case: _nocat below its cap -> the flat catch-all stays so
    # null-category / legacy / rolling-upgrade jobs still have a consumer.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    w = _mt_worker(r)
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {gw.NULL_CATEGORY: 2}  # _nocat 0/2 -> under cap
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.maintenance" in names  # catch-all kept while _nocat has room


def test_fair_ordered_queues_floor_keeps_flat_catchall_at_nocat_cap():
    # The ungoverned floor never drops the catch-all, even at the _nocat cap.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd(gw.category_running_key("P", gw.NULL_CATEGORY), "x")
    w = _mt_worker(r)
    w._floor = True
    w.queue_class = _NameQueue
    w.gov_category_max_inflight = {gw.NULL_CATEGORY: 1}
    w._ordered_queues = _ordered(["storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._fair_ordered_queues(defer_bg=False)]
    assert "storage.P.maintenance" in names  # floor serves the catch-all regardless


# --- flat (multitenancy OFF) drain of stray per-category lanes ---------------


def test_flat_ordered_queues_is_pure_base_without_strays():
    # Steady OFF state: no per-category lane exists -> exactly the base set, no
    # discovery-driven additions (zero behaviour change vs pre-Phase-2).
    r = _FakeRedis()
    w = _worker(r)  # multitenancy False
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.maintenance", "storage.P.interactive"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._flat_ordered_queues(defer_bg=False)]
    assert names == ["storage.P.maintenance", "storage.P.interactive"]


def test_flat_ordered_queues_drains_stray_category_lanes_when_off():
    # Rollout safety (adversarial finding): a producer emitting per-category lanes
    # before this worker is recreated ON, or leftover jobs after flipping back OFF,
    # must still be drained — an OFF worker that ignored them would strand them.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd("rq:queues", "rq:queue:storage.P.catB.bulk")
    w = _worker(r)  # multitenancy False
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.bulk", "storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._flat_ordered_queues(defer_bg=False)]
    assert names[:2] == ["storage.P.bulk", "storage.P.maintenance"]  # base first
    assert set(names[2:]) == {
        "storage.P.catA.maintenance",
        "storage.P.catB.bulk",
    }  # stray lanes appended for drain


def test_flat_ordered_queues_defer_bg_hides_maintenance_strays():
    # While deferring heavy work, an OFF worker drops maintenance base AND maintenance
    # stray lanes, but still drains bulk strays.
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    r.sadd("rq:queues", "rq:queue:storage.P.catB.bulk")
    w = _worker(r)
    w.queue_class = _NameQueue
    w._ordered_queues = _ordered(["storage.P.bulk", "storage.P.maintenance"])
    w._fair_targets = w._derive_fair_targets()
    names = [q.name for q in w._flat_ordered_queues(defer_bg=True)]
    assert not any("maintenance" in n for n in names)  # all heavy hidden
    assert "storage.P.bulk" in names and "storage.P.catB.bulk" in names


# --- #3: bg-floor round-robins heavy tiers so none starves under pressure -----


def test_floor_round_robins_heavy_tiers_flat():
    # The ungoverned bg-floor is the only heavy drainer once every governed pool
    # defers under sustained pressure. A fixed dequeue order would starve template
    # and reclaim behind a steady maintenance/bulk trickle; the floor must rotate.
    r = _FakeRedis()
    w = _worker(r)  # multitenancy off -> _flat_ordered_queues
    w._floor = True
    w.queue_class = _NameQueue
    tiers = [
        "storage.P.maintenance",
        "storage.P.reclaim",
        "storage.P.bulk",
        "storage.P.template",
    ]
    w._ordered_queues = _ordered(tiers)
    w._fair_targets = w._derive_fair_targets()
    leads = {w._flat_ordered_queues(defer_bg=False)[0].name for _ in range(4)}
    assert leads == set(tiers)  # every tier leads on some poll -> none starves


def test_floor_round_robins_heavy_tiers_multitenancy():
    r = _FakeRedis()
    w = _mt_worker(r)  # multitenancy on -> _fair_ordered_queues
    w._floor = True
    w.queue_class = _NameQueue
    tiers = [
        "storage.P.maintenance",
        "storage.P.reclaim",
        "storage.P.bulk",
        "storage.P.template",
    ]
    w._ordered_queues = _ordered(tiers)
    w._fair_targets = w._derive_fair_targets()
    leads = {w._fair_ordered_queues(defer_bg=False)[0].name for _ in range(4)}
    assert leads == set(tiers)  # catch-all lanes rotate -> every tier leads


def test_nonfloor_keeps_strict_tier_priority_order():
    # Governed workers must NOT rotate: strict tier priority is by design
    # (template preempts reclaim), so the lead lane is stable across polls.
    r = _FakeRedis()
    w = _worker(r)  # _floor False
    w.queue_class = _NameQueue
    tiers = [
        "storage.P.template",
        "storage.P.bulk",
        "storage.P.maintenance",
        "storage.P.reclaim",
    ]
    w._ordered_queues = _ordered(tiers)
    w._fair_targets = w._derive_fair_targets()
    leads = {w._flat_ordered_queues(defer_bg=False)[0].name for _ in range(4)}
    assert leads == {"storage.P.template"}  # highest tier always leads


# --- fair admit / release ---


def test_admit_maintenance_reserves_both_fair_slots():
    r = _FakeRedis()
    w = _mt_worker(r, max_heavy=2)
    job = _Job("j1")
    assert w._admit(job, _Q("storage.P.catA.maintenance"), defer_bg=False) is True
    assert job._gov_reserved == ("fair", "P", "catA", True)
    assert r.scard(gw.category_running_key("P", "catA")) == 1
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1


def test_admit_bulk_reserves_only_category():
    r = _FakeRedis()
    w = _mt_worker(r)
    job = _Job("j1")
    assert w._admit(job, _Q("storage.P.catA.bulk"), defer_bg=False) is True
    assert job._gov_reserved == ("fair", "P", "catA", False)
    assert r.scard(gw.category_running_key("P", "catA")) == 1
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0  # bulk never takes the heavy slot


def test_admit_null_category_base_queue_routes_to_sentinel():
    r = _FakeRedis()
    w = _mt_worker(r)
    job = _Job("j1")
    # a job off the flat catch-all (category None) -> the NULL_CATEGORY lane
    assert w._admit(job, _Q("storage.P.maintenance"), defer_bg=False) is True
    assert job._gov_reserved == ("fair", "P", gw.NULL_CATEGORY, True)
    assert r.scard(gw.category_running_key("P", gw.NULL_CATEGORY)) == 1


def test_admit_denies_and_pushes_back_when_category_at_cap():
    r = _FakeRedis()
    r.sadd(gw.category_running_key("P", "catA"), "x")  # at cap 1
    w = _mt_worker(r)
    w.gov_category_max_inflight = {"catA": 1}
    q = _Q("storage.P.catA.bulk")
    job = _Job("j1")
    assert w._admit(job, q, defer_bg=False) is False
    assert q.pushed == ("j1", True)  # re-enqueued at the FRONT
    assert not hasattr(job, "_gov_reserved")


def test_admit_maintenance_deferred_pushes_back():
    r = _FakeRedis()
    w = _mt_worker(r)
    q = _Q("storage.P.catA.maintenance")
    job = _Job("j1")
    assert w._admit(job, q, defer_bg=True) is False
    assert q.pushed == ("j1", True)
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0


def test_admit_kill_switch_runs_fair_tier_ungoverned():
    r = _FakeRedis()
    w = _mt_worker(r)
    w.gov_enabled = False  # kill-switch: gating off, discovery/shape stay on
    job = _Job("j1")
    assert w._admit(job, _Q("storage.P.catA.maintenance"), defer_bg=False) is True
    assert not hasattr(job, "_gov_reserved")  # ungoverned -> no reservation
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0


def test_admit_floor_runs_ungoverned():
    r = _FakeRedis()
    w = _mt_worker(r)
    w._floor = True
    job = _Job("j1")
    assert w._admit(job, _Q("storage.P.catA.maintenance"), defer_bg=False) is True
    assert not hasattr(job, "_gov_reserved")
    assert r.scard(gw.category_running_key("P", "catA")) == 0


# --- execute_job release via the per-job reserved flag ---


def test_execute_job_releases_fair_slots(monkeypatch):
    monkeypatch.setattr(gw.Worker, "execute_job", lambda self, job, queue: "ran")
    r = _FakeRedis()
    w = _mt_worker(r, max_heavy=2)
    q = _Q("storage.P.catA.maintenance")
    job = _Job("j1")
    w._admit(job, q, defer_bg=False)
    assert r.scard(gw.category_running_key("P", "catA")) == 1
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1
    w.execute_job(job, q)  # finally-block releases exactly what was reserved
    assert r.scard(gw.category_running_key("P", "catA")) == 0
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 0


def test_execute_job_no_release_without_flag(monkeypatch):
    monkeypatch.setattr(gw.Worker, "execute_job", lambda self, job, queue: "ran")
    r = _FakeRedis({"keep"})  # heavy set holds an unrelated id
    w = _mt_worker(r)
    job = _Job("j1")  # ungoverned: no _gov_reserved flag
    w.execute_job(job, _Q("storage.P.catA.maintenance"))
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1  # untouched (counter-neutral)


# --- end-to-end dequeue under multitenancy ---


class _MTQueue:
    """Queue stand-in with a class-level name->job-id store and a classmethod
    dequeue_any, so the full dequeue path (discover -> order -> BLPOP -> admit)
    can be driven and asserted by ACTUAL job pickup, not counters."""

    store = {}

    def __init__(self, name, connection=None, job_class=None, serializer=None):
        self.name = name

    def push_job_id(self, jid, at_front=False):
        q = _MTQueue.store.setdefault(self.name, [])
        q.insert(0, jid) if at_front else q.append(jid)

    @classmethod
    def dequeue_any(
        cls,
        queues,
        timeout,
        connection=None,
        job_class=None,
        serializer=None,
        death_penalty_class=None,
    ):
        for q in queues:
            lst = cls.store.get(q.name)
            if lst:
                return (_Job(lst.pop(0)), q)
        raise DequeueTimeout(timeout, [])


def test_dequeue_multitenancy_discovers_and_reserves_category(tmp_path):
    _MTQueue.store = {"storage.P.catA.maintenance": ["j1"]}
    r = _FakeRedis()
    r.sadd("rq:queues", "rq:queue:storage.P.catA.maintenance")
    w = _worker(
        r,
        cpu_path=_psi_file(tmp_path, "cpu", 1.0),
        io_path=_psi_file(tmp_path, "io", 1.0),
        max_heavy=2,
    )
    w.multitenancy = True
    w.queue_class = _MTQueue
    w._ordered_queues = [
        _MTQueue("storage.P.maintenance"),
        _MTQueue("storage.P.interactive"),
    ]
    w._fair_targets = w._derive_fair_targets()
    job, queue = w.dequeue_job_and_maintain_ttl(10)
    assert (job.id, queue.name) == ("j1", "storage.P.catA.maintenance")
    assert job._gov_reserved == ("fair", "P", "catA", True)
    assert r.scard(gw.category_running_key("P", "catA")) == 1
    assert r.scard(gw.HEAVY_RUNNING_KEY) == 1


# --- observability: _publish_status + last-job stamping (P2.4 §3) ------------
#
# The ONE worker-side write for the storage-governor observability read layer.
# These pin the published contract the apiv4 reader depends on: a self-expiring
# ``governor:worker:<name>`` HASH, JSON served_lanes, "1"/"0" flags, repr'd PSI
# floats, and last-job attribution — plus the invariant that a Redis blip in the
# hot dequeue path can never raise out of the publish.


def _publish_worker(
    connection, tmp_path, cpu=12.0, io=3.0, mem=2.0, name="w1", queues=None
):
    w = _worker(
        connection,
        _psi_file(tmp_path, "cpu", cpu),
        _psi_file(tmp_path, "io", io),
        mem_path=_psi_file(tmp_path, "mem", mem),
    )
    w.name = name
    w._last_job_id = None
    w._last_job_action = None
    w._ordered_queues = [
        _Q(q)
        for q in (queues or ["storage.default.bulk", "storage.default.maintenance"])
    ]
    # Derive fair targets from the ordered queues, as GovernedWorker.__init__
    # does, so _worker_kind() reflects the served tiers (elastic vs reserved).
    w._fair_targets = w._derive_fair_targets()
    return w


def test_publish_status_writes_self_expiring_hash(tmp_path):
    r = _FakeRedis()
    w = _publish_worker(r, tmp_path, cpu=12.5, io=4.0, mem=6.5)
    w._publish_status(False)

    key = gw.worker_status_key("w1")
    h = r.hgetall(key)
    assert h  # hash written
    assert h["kind"] == "elastic"  # serves fair tiers
    assert h["governing"] == "1"
    assert h["deferring"] == "0"
    assert h["multitenancy"] == "0"
    assert h["floor"] == "0"
    # served_lanes is a JSON list of the structural base set (coverage signal).
    assert json.loads(h["served_lanes"]) == [
        "storage.default.bulk",
        "storage.default.maintenance",
    ]
    assert h["pool"] == "default"
    # PSI floats are repr'd -> the reader float()s them back.
    assert float(h["psi_cpu"]) == 12.5
    assert float(h["psi_io"]) == 4.0
    assert float(h["psi_mem"]) == 6.5  # memory-PSI surfaced to the read layer
    # self-expires so a dead worker's row disappears (reader -> "down").
    assert r._expires[key] == gw._WORKER_STATUS_TTL


def test_publish_status_deferring_and_multitenancy_flags(tmp_path):
    r = _FakeRedis()
    w = _publish_worker(r, tmp_path)
    w.multitenancy = True
    w._publish_status(True)  # this poll is deferring maintenance
    h = r.hgetall(gw.worker_status_key("w1"))
    assert h["deferring"] == "1"
    assert h["multitenancy"] == "1"


def test_publish_status_last_job_included_when_set_and_omitted_when_none(tmp_path):
    r = _FakeRedis()
    w = _publish_worker(r, tmp_path)
    # None -> keys absent so the reader degrades (never publishes a stale/empty id)
    w._publish_status(False)
    h = r.hgetall(gw.worker_status_key("w1"))
    assert "last_job_id" not in h
    assert "last_job_action" not in h
    # set -> exact attribution fields present
    w._last_job_id = "task-abc"
    w._last_job_action = "convert"
    w._publish_status(False)
    h = r.hgetall(gw.worker_status_key("w1"))
    assert h["last_job_id"] == "task-abc"
    assert h["last_job_action"] == "convert"


def test_publish_status_kind_reserved_and_floor(tmp_path):
    # No fair targets -> reserved.
    r = _FakeRedis()
    w = _publish_worker(r, tmp_path, queues=["storage.default.interactive"])
    w._publish_status(False)
    assert r.hgetall(gw.worker_status_key("w1"))["kind"] == "reserved"
    # bg-floor worker -> floor, and governing is off.
    r2 = _FakeRedis()
    w2 = _publish_worker(r2, tmp_path, name="w2")
    w2._floor = True
    w2._publish_status(False)
    h = r2.hgetall(gw.worker_status_key("w2"))
    assert h["kind"] == "floor"
    assert h["governing"] == "0"
    assert h["floor"] == "1"


def test_publish_status_never_raises_on_redis_error(tmp_path):
    class _Boom(_FakeRedis):
        def pipeline(self):
            raise RuntimeError("redis down")

    w = _publish_worker(_Boom(), tmp_path)
    # Must not propagate — a blip here would wedge the hot dequeue loop.
    assert w._publish_status(False) is None


def test_execute_job_stamps_last_job_id_and_action(monkeypatch):
    monkeypatch.setattr(
        gw.Worker, "execute_job", lambda self, job, queue: ("ran", job.id)
    )
    w = _worker(_FakeRedis())
    w._last_job_id = None
    w._last_job_action = None

    class _EJob:
        id = "task-xyz"
        func_name = "task.convert"

    result = w.execute_job(_EJob(), _Q("storage.default.maintenance"))
    assert result == ("ran", "task-xyz")
    # stamped BEFORE super().execute_job -> visible to the next status publish
    # even if the work-horse is then SIGKILLed by a poison job.
    assert w._last_job_id == "task-xyz"
    assert w._last_job_action == "convert"
