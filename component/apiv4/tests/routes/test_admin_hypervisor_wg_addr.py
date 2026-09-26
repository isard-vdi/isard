# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dhcp hook may only give a guest ip to a desktop that is running."""

import pytest
from isardvdi_common.helpers.caches import Caches
from rethinkdb import r
from rethinkdb_mock import MockThink
from tests.routes.helpers import MockJWT

MAC = "52:54:00:2c:7a:13"
URL = "/admin/item/hypervisor/vm/wg_addr"


@pytest.fixture(autouse=True)
def clean_cache():
    Caches.wg_mac_domain_cache.clear()
    yield
    Caches.wg_mac_domain_cache.clear()


@pytest.fixture
def report(test_client_with_conn):
    def post(domains, ip="192.0.2.75"):
        tables = {
            "config": [{"id": 1, "maintenance": False}],
            "categories": [{"id": "default"}],
            "domains": domains,
        }
        mock_db = MockThink({"dbs": {"isard": {"tables": tables}}, "default": "isard"})
        with mock_db.connect() as conn:
            response = test_client_with_conn(
                db_tables_data=tables,
                conn=conn,
                url=URL,
                method="POST",
                body={"mac": MAC, "ip": ip},
                jwt=MockJWT(),
            )
            rows = {d["id"]: d for d in r.table("domains").run(conn)}
        return response, rows

    return post


def _desktop(status):
    return {"id": "desktop-1", "kind": "desktop", "status": status}


@pytest.mark.parametrize("status", ["Starting", "StartingDomainDisposable", "Started"])
def test_a_running_desktop_gets_its_ip(report, status):
    Caches.wg_mac_domain_cache[MAC] = "desktop-1"

    response, rows = report([_desktop(status)])

    assert response.status_code == 200
    assert response.json() == {"domain_id": "desktop-1"}
    assert rows["desktop-1"]["viewer"] == {"guest_ip": "192.0.2.75"}


@pytest.mark.parametrize("status", ["Stopped", "Stopping", "Failed", "Shutting-down"])
def test_a_desktop_that_stopped_while_its_mac_was_cached_gets_nothing(report, status):
    Caches.wg_mac_domain_cache[MAC] = "desktop-1"

    response, rows = report([_desktop(status)], ip="192.0.2.99")

    assert response.status_code == 404
    assert "viewer" not in rows["desktop-1"]
    assert MAC not in Caches.wg_mac_domain_cache


def test_a_cached_desktop_that_no_longer_exists_is_not_found(report):
    Caches.wg_mac_domain_cache[MAC] = "desktop-1"

    response, rows = report([])

    assert response.status_code == 404
    assert rows == {}
    assert MAC not in Caches.wg_mac_domain_cache
