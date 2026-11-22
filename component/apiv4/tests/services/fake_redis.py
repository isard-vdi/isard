# SPDX-License-Identifier: AGPL-3.0-or-later

"""The few redis commands the storage batches use, in memory, answering bytes like the real client."""


def _b(value):
    return value if isinstance(value, bytes) else str(value).encode()


class FakeRedis:
    def __init__(self):
        self.data = {}

    def pipeline(self):
        return _Pipeline(self)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = _b(value)
        return True

    def get(self, key):
        return self.data.get(key)

    def exists(self, key):
        return int(key in self.data)

    def delete(self, key):
        return int(self.data.pop(key, None) is not None)

    def expire(self, key, seconds):
        return int(key in self.data)

    def hset(self, key, field=None, value=None, mapping=None):
        h = self.data.setdefault(key, {})
        for k, v in (mapping or {field: value}).items():
            h[_b(k)] = _b(v)
        return 1

    def hget(self, key, field):
        return self.data.get(key, {}).get(_b(field))

    def hgetall(self, key):
        return dict(self.data.get(key, {}))

    def hincrby(self, key, field, amount=1):
        h = self.data.setdefault(key, {})
        h[_b(field)] = _b(int(h.get(_b(field), b"0")) + amount)
        return int(h[_b(field)])

    def rpush(self, key, *values):
        self.data.setdefault(key, []).extend(_b(v) for v in values)
        return len(self.data[key])

    def lindex(self, key, index):
        items = self.data.get(key, [])
        return items[index] if 0 <= index < len(items) else None

    def sadd(self, key, *members):
        self.data.setdefault(key, set()).update(_b(m) for m in members)
        return 1

    def srem(self, key, *members):
        self.data.get(key, set()).difference_update(_b(m) for m in members)
        return 1

    def smembers(self, key):
        return set(self.data.get(key, set()))


class _Pipeline:
    def __init__(self, redis):
        self.redis, self.calls = redis, []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.calls.append((getattr(self.redis, name), args, kwargs))
            return self

        return queue

    def execute(self):
        return [call(*args, **kwargs) for call, args, kwargs in self.calls]
