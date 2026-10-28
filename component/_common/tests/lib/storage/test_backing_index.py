# SPDX-License-Identifier: AGPL-3.0-or-later

"""The shared, incremental, signature-validated backing index: reuse of
unchanged headers, re-read of changed/unreadable ones, persistence of a slice a
timed-out worker managed to flush, cooperative work-splitting, and the
Redis-down fallback. These are the properties that make a cold 45k-file estate
index once across the fleet instead of once per worker per retry."""

import json

from isardvdi_common.lib.storage import backing_index

KEY = backing_index.DEFAULT_KEY


class FakeHashRedis:
    """A dict-backed stand-in for the hash ops the index uses."""

    def __init__(self):
        self.h = {}

    def hgetall(self, key):
        return dict(self.h.get(key, {}))

    def hmget(self, key, fields):
        d = self.h.get(key, {})
        return [d.get(f) for f in fields]

    def hset(self, key, mapping=None, **kw):
        d = self.h.setdefault(key, {})
        if mapping:
            d.update(
                {
                    k: (v.encode() if isinstance(v, str) else v)
                    for k, v in mapping.items()
                }
            )
        return len(mapping or {})

    def expire(self, key, ttl):
        return True

    def hdel(self, key, *fields):
        d = self.h.get(key, {})
        return sum(1 for f in fields if d.pop(f, None) is not None)


def _entry(readable=True, backing=None):
    return {
        "uuid": None,
        "size": 1,
        "backing_raw": backing,
        "backing_path": backing,
        "backing_uuid": None,
        "readable": readable,
    }


def _files(tmp_path, n, content=b"x"):
    paths = []
    for i in range(n):
        p = tmp_path / f"{i}.qcow2"
        p.write_bytes(content)
        paths.append(str(p))
    return paths


def test_unchanged_files_are_reused_not_reread(tmp_path):
    paths = _files(tmp_path, 2)
    reads = []

    def build(ps):
        reads.append(list(ps))
        return {p: _entry() for p in ps}

    r = FakeHashRedis()
    idx1 = backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    assert set(idx1) == set(paths)
    reads.clear()
    idx2 = backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    assert set(idx2) == set(paths)
    assert reads == []  # cache warm: no header re-read


def test_a_changed_file_is_reread(tmp_path):
    paths = _files(tmp_path, 1)
    calls = []

    def build(ps):
        calls.append(list(ps))
        return {p: _entry() for p in ps}

    r = FakeHashRedis()
    backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    # change the size -> signature changes -> must be re-read
    open(paths[0], "wb").write(b"xx")
    backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    assert calls == [paths, paths]


def test_an_unreadable_entry_is_never_cached(tmp_path):
    paths = _files(tmp_path, 1)
    calls = []

    def build(ps):
        calls.append(list(ps))
        return {p: _entry(readable=False) for p in ps}

    r = FakeHashRedis()
    backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    assert calls == [paths, paths]  # re-read every pass
    assert r.h.get(KEY, {}) == {}  # nothing persisted


def test_a_partial_build_persists_its_slice_for_the_next_pass(tmp_path):
    """THE incident property: a worker killed partway through the build still
    leaves the slice it flushed, so the next pass continues instead of starting
    from zero. Red on main (the whole-index set ran only after the full build,
    which never finished, so nothing was ever cached)."""
    paths = _files(tmp_path, 5)

    class Boom(Exception):
        pass

    reads = []

    def build_partial(ps):
        reads.append(list(ps))
        if len(reads) > 1:  # die on the second chunk, like a JobTimeoutException
            raise Boom()
        return {p: _entry() for p in ps}

    r = FakeHashRedis()
    try:
        backing_index.shared_backing_index(
            lambda: paths, build_partial, r, shuffle=False, flush=2
        )
    except Boom:
        pass
    assert len(r.h.get(KEY, {})) == 2  # first chunk survived the crash

    reads2 = []

    def build_rest(ps):
        reads2.append(list(ps))
        return {p: _entry() for p in ps}

    idx = backing_index.shared_backing_index(
        lambda: paths, build_rest, r, shuffle=False, flush=2
    )
    assert set(idx) == set(paths)
    assert sum(len(c) for c in reads2) == 3  # only the remaining 3 re-read


def test_between_chunk_reclaim_skips_what_a_sibling_flushed(tmp_path):
    """Cooperative work-splitting: between chunks a worker drops paths a sibling
    has flushed, so two workers split the headers instead of both reading all."""
    paths = _files(tmp_path, 3)
    r = FakeHashRedis()
    reads = []

    def build(ps):
        reads.append(list(ps))
        # a "sibling" flushes the last path right after our first chunk
        bucket = r.h.setdefault(KEY, {})
        if paths[2] not in bucket:
            bucket[paths[2]] = json.dumps(
                {"sig": backing_index.file_signature(paths[2]), "e": _entry()}
            ).encode()
        return {p: _entry() for p in ps}

    idx = backing_index.shared_backing_index(
        lambda: paths, build, r, shuffle=False, flush=1
    )
    assert set(idx) == set(paths)
    read_paths = [p for chunk in reads for p in chunk]
    assert paths[2] not in read_paths  # reclaimed, never built here


def test_redis_down_builds_everything_with_a_correct_answer(tmp_path):
    paths = _files(tmp_path, 3)

    def build(ps):
        return {p: _entry() for p in ps}

    idx = backing_index.shared_backing_index(lambda: paths, build, None, shuffle=False)
    assert set(idx) == set(paths)


def test_a_redis_that_raises_degrades_to_a_full_build(tmp_path):
    paths = _files(tmp_path, 2)

    class AngryRedis:
        def hgetall(self, *a, **k):
            raise RuntimeError("down")

        def hmget(self, *a, **k):
            raise RuntimeError("down")

        def hset(self, *a, **k):
            raise RuntimeError("down")

        def expire(self, *a, **k):
            raise RuntimeError("down")

        def hdel(self, *a, **k):
            raise RuntimeError("down")

    def build(ps):
        return {p: _entry() for p in ps}

    idx = backing_index.shared_backing_index(
        lambda: paths, build, AngryRedis(), shuffle=False
    )
    assert set(idx) == set(paths)  # correct answer despite every Redis op failing


def test_vanished_paths_are_pruned_from_the_cache(tmp_path):
    paths = _files(tmp_path, 2)

    def build(ps):
        return {p: _entry() for p in ps}

    r = FakeHashRedis()
    backing_index.shared_backing_index(lambda: paths, build, r, shuffle=False)
    assert len(r.h.get(KEY, {})) == 2
    # one file disappears from the candidate list on the next pass
    backing_index.shared_backing_index(lambda: paths[:1], build, r, shuffle=False)
    assert set(r.h.get(KEY, {})) == {paths[0]}
