import fnmatch


class FakeRedis:
    """The hash commands Presence and count_connected use, with TTLs kept but not ticking."""

    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def _hset(self, key, field=None, value=None, mapping=None):
        h = self.hashes.setdefault(key, {})
        if field is not None:
            h[field] = value
        h.update(mapping or {})

    def _delete(self, key):
        self.hashes.pop(key, None)
        self.ttls.pop(key, None)

    def _expire(self, key, seconds):
        if key in self.hashes:
            self.ttls[key] = seconds

    def _hdel(self, key, field):
        h = self.hashes.get(key, {})
        h.pop(field, None)
        if not h:
            self._delete(key)

    def expire_now(self, key):
        if key in self.ttls:
            self._delete(key)

    def pipeline(self, transaction=True):
        return _Pipeline(self)

    async def hdel(self, key, field):
        self._check()
        self._hdel(key, field)

    async def delete(self, key):
        self._check()
        self._delete(key)

    def sync(self):
        return _SyncView(self)


class _Pipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def hset(self, *args, **kwargs):
        self.ops.append((self.redis._hset, args, kwargs))

    def expire(self, *args):
        self.ops.append((self.redis._expire, args, {}))

    def delete(self, *args):
        self.ops.append((self.redis._delete, args, {}))

    async def execute(self):
        self.redis._check()
        for op, args, kwargs in self.ops:
            op(*args, **kwargs)


class _SyncView:
    def __init__(self, redis):
        self.redis = redis

    def scan_iter(self, match, count=None):
        return [k for k in list(self.redis.hashes) if fnmatch.fnmatch(k, match)]

    def hvals(self, key):
        return list(self.redis.hashes.get(key, {}).values())
