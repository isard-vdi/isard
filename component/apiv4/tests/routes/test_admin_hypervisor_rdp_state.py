# SPDX-License-Identifier: AGPL-3.0-or-later
"""The vpn may only store an RDP state on the desktop that is running with that guest ip."""

import pytest
from rethinkdb import r
from rethinkdb_mock import MockThink
from tests.routes.helpers import MockJWT

URL = "/admin/item/hypervisor/vm/rdp_state"


@pytest.fixture
def report(test_client_with_conn):
    def post(domains, body):
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
                body=body,
                jwt=MockJWT(),
            )
            rows = {d["id"]: d for d in r.table("domains").run(conn)}
        return response, rows

    return post


def _desktop(status="Started", ip="192.0.2.75", rdp=None):
    viewer = {"guest_ip": ip, "passwd": "x"}
    if rdp:
        viewer["rdp"] = rdp
    return {"id": "desktop-1", "kind": "desktop", "status": status, "viewer": viewer}


def _body(state="ready", ip="192.0.2.75", **extra):
    return {"domain_id": "desktop-1", "ip": ip, "state": state, **extra}


def test_a_running_desktop_gets_its_rdp_state(report):
    response, rows = report([_desktop()], _body(protocol="nla"))

    assert response.status_code == 204
    viewer = rows["desktop-1"]["viewer"]
    assert viewer["guest_ip"] == "192.0.2.75"
    assert viewer["rdp"]["state"] == "ready"
    assert viewer["rdp"]["protocol"] == "nla"


def test_a_new_state_replaces_the_old_one_whole(report):
    old = {"state": "refused", "reason": "nla_required", "at": 1}
    response, rows = report([_desktop(rdp=old)], _body(state="waiting"))

    assert response.status_code == 204
    assert rows["desktop-1"]["viewer"]["rdp"]["state"] == "waiting"
    assert rows["desktop-1"]["viewer"]["rdp"].get("reason") is None


@pytest.mark.parametrize(
    "desktop", [_desktop(status="Stopped"), _desktop(ip="192.0.2.99")]
)
def test_a_desktop_not_running_with_that_ip_gets_nothing(report, desktop):
    response, rows = report([desktop], _body())

    assert response.status_code == 404
    assert "rdp" not in rows["desktop-1"]["viewer"]


def test_an_unknown_state_is_rejected(report):
    response, _ = report([_desktop()], _body(state="maybe"))

    assert response.status_code == 400
