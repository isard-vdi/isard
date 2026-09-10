#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Declared coverage against live coverage.

Counting only powered-on nodes cannot tell "nobody serves this pool" from "the
nodes that serve it are asleep". They are opposite situations: one is an orphan
lane, the other is work that has only to wait. Measured in the field on a fleet
running 1 of 13 hypervisors, where every pool served by the sleeping twelve read
as a problem.
"""

from isardvdi_common.lib.storage.storage_pools import storage_pools as mod

SPP = mod.StoragePoolsProcessed
STALE = 7 * 24 * 3600
NOW = 1_800_000_000


def test_an_online_node_always_counts():
    assert SPP.declaration_counts({"status": "Online", "status_time": 0}, NOW, STALE)


def test_a_sleeping_node_still_counts_while_it_is_expected_back():
    node = {"status": "Offline", "status_time": NOW - 3600}
    assert SPP.declaration_counts(node, NOW, STALE)


def test_a_node_that_has_been_gone_too_long_stops_counting():
    """Otherwise a decommissioned row nobody deleted silences the orphan alarm
    for ever, which is the true positive this split must not lose."""
    node = {"status": "Offline", "status_time": NOW - STALE - 1}
    assert not SPP.declaration_counts(node, NOW, STALE)


def test_a_declaration_with_no_timestamp_is_treated_as_ancient():
    assert not SPP.declaration_counts({"status": "Offline"}, NOW, STALE)


def test_the_category_warning_reads_the_declared_half(monkeypatch):
    """A category assigned to a pool whose nodes are merely asleep is not a
    warning: the disks will route as soon as one comes back."""
    # live 0 everywhere: only the declared half may decide
    monkeypatch.setattr(SPP, "_pool_coverage", classmethod(lambda c, i: 0))

    monkeypatch.setattr(SPP, "_pool_coverage_declared", classmethod(lambda c, i: 2))
    assert SPP._category_consumer_warning("p") is None

    monkeypatch.setattr(SPP, "_pool_coverage_declared", classmethod(lambda c, i: 0))
    assert SPP._category_consumer_warning("p")["code"] == (
        "storage_pool_category_no_consumer"
    )
