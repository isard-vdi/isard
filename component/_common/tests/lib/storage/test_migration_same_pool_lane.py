# SPDX-License-Identifier: AGPL-3.0-or-later

"""A move inside one pool must land on a lane a worker actually serves."""

from types import SimpleNamespace

from isardvdi_common.models.storage import get_queue_from_storage_pools


class _Pool(SimpleNamespace):
    """Stands in for StoragePool: equality by id, which is what the queue"""

    def __eq__(self, other):
        return isinstance(other, _Pool) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


def test_same_pool_uses_the_plain_pool_lane():
    p = _Pool(id="pool-a")
    assert get_queue_from_storage_pools(p, _Pool(id="pool-a")) == "pool-a"


def test_two_pools_use_the_sorted_pair_lane():
    a, b = _Pool(id="bbb"), _Pool(id="aaa")
    # sorted, so both directions name the one lane the worker subscribes to
    assert get_queue_from_storage_pools(a, b) == "aaa:bbb"
    assert get_queue_from_storage_pools(b, a) == "aaa:bbb"
