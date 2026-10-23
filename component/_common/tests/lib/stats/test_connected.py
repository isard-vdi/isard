# SPDX-License-Identifier: AGPL-3.0-or-later

import fnmatch

from isardvdi_common.lib.stats.connected import KEY_PREFIX, count_connected


class _Redis:
    def __init__(self, hashes):
        self.hashes = hashes

    def scan_iter(self, match, count=None):
        return [k for k in self.hashes if fnmatch.fnmatch(k, match)]

    def hvals(self, key):
        return list(self.hashes[key].values())


def test_users_are_distinct_across_processes():
    redis = _Redis(
        {
            f"{KEY_PREFIX}web-1": {"s1": b"u1", "s2": b"u1", "s3": b"u2"},
            f"{KEY_PREFIX}web-2": {"s4": b"u1", "s5": b""},
            "socketio:other": {"s6": b"u9"},
        }
    )
    assert count_connected(redis) == {"users": 2, "sockets": 5}


def test_nothing_connected():
    assert count_connected(_Redis({})) == {"users": 0, "sockets": 0}
