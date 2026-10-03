#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Connections and ERR replies that repeated short redis calls cost the real server."""

import redis as redis_lib
from isardvdi_common.connections.redis_client import shared_client
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.helpers import resource_lock

CALLS = 20


def _counters():
    info = redis_lib.from_url(rq_url(), protocol=2).info("all")
    return (
        info["total_connections_received"],
        info.get("errorstat_ERR", {}).get("count", 0),
    )


def test_short_calls_share_one_connection_and_raise_no_error():
    conns_before, errors_before = _counters()
    for _ in range(CALLS):
        shared_client(rq_url()).ping()
    conns_after, errors_after = _counters()

    assert conns_after - conns_before <= 4
    assert errors_after - errors_before == 0


def test_repeated_resource_locks_share_one_connection_and_raise_no_error():
    conns_before, errors_before = _counters()
    for _ in range(CALLS):
        with resource_lock.resource_lock("integration-shared-client"):
            pass
    conns_after, errors_after = _counters()

    assert conns_after - conns_before <= 4
    assert errors_after - errors_before == 0
