#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``wg_mac_domain_cache`` invalidation by the identifier callers actually hold.

The map is keyed by wireguard MAC, but the only caller that invalidates it
holds a *domain id*, so it needs a lookup by value. These are unit tests of
the helper itself; the regression test for the call site that was passing the
wrong identifier lives in the change-handler suite
(``test_domains_handler.py::TestWireguardMacCacheInvalidation``).
"""

import pytest
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache


@pytest.fixture(autouse=True)
def clean_cache():
    Caches.wg_mac_domain_cache.clear()
    yield
    Caches.wg_mac_domain_cache.clear()


class TestInvalidateByDomainId:
    def test_drops_the_entry_for_that_domain(self):
        Caches.set_cached_domain_wg_mac(
            "desktop-1", [{"id": "wireguard", "mac": "52:54:00:2c:7a:13"}]
        )

        Caches.invalidate_cached_domain_wg_mac_by_domain_id("desktop-1")

        assert "52:54:00:2c:7a:13" not in Caches.wg_mac_domain_cache

    def test_leaves_other_domains_alone(self):
        Caches.set_cached_domain_wg_mac(
            "desktop-1", [{"id": "wireguard", "mac": "52:54:00:2c:7a:13"}]
        )
        Caches.set_cached_domain_wg_mac(
            "desktop-2", [{"id": "wireguard", "mac": "52:54:00:aa:bb:cc"}]
        )

        Caches.invalidate_cached_domain_wg_mac_by_domain_id("desktop-1")

        assert "52:54:00:2c:7a:13" not in Caches.wg_mac_domain_cache
        assert Caches.wg_mac_domain_cache["52:54:00:aa:bb:cc"] == "desktop-2"

    def test_drops_every_mac_mapped_to_that_domain(self):
        Caches.wg_mac_domain_cache["52:54:00:2c:7a:13"] = "desktop-1"
        Caches.wg_mac_domain_cache["52:54:00:de:ad:be"] = "desktop-1"

        Caches.invalidate_cached_domain_wg_mac_by_domain_id("desktop-1")

        assert len(Caches.wg_mac_domain_cache) == 0

    def test_unknown_domain_id_is_a_noop(self):
        Caches.wg_mac_domain_cache["52:54:00:2c:7a:13"] = "desktop-1"

        Caches.invalidate_cached_domain_wg_mac_by_domain_id("desktop-nope")

        assert Caches.wg_mac_domain_cache["52:54:00:2c:7a:13"] == "desktop-1"


class _Clock:
    """Manually advanced monotonic clock, so the TTL never needs a real wait."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class _ExpireWhenScanned:
    """Cache value that trips the clock past the TTL as the scan compares it.

    Reproduces the race deterministically: the entry is live when the scan
    reads it and expired by the time the delete runs.
    """

    def __init__(self, domain_id, clock, ttl):
        self.domain_id = domain_id
        self._clock = clock
        self._ttl = ttl

    def __eq__(self, other):
        self._clock.advance(self._ttl + 1)
        return self.domain_id == other


class TestEntryExpiringMidScan:
    def test_expiry_between_scan_and_delete_does_not_raise(self, monkeypatch):
        clock = _Clock()
        ttl = 200
        cache = SynchronizedTTLCache(maxsize=50, ttl=ttl, timer=clock)
        monkeypatch.setattr(Caches, "wg_mac_domain_cache", cache)
        cache["52:54:00:2c:7a:13"] = _ExpireWhenScanned("desktop-1", clock, ttl)

        Caches.invalidate_cached_domain_wg_mac_by_domain_id("desktop-1")

        assert "52:54:00:2c:7a:13" not in cache
