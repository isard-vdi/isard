# SPDX-License-Identifier: AGPL-3.0-or-later

"""A restored domain never comes back in a status only the engine can finish."""

import os

import pytest
from isardvdi_common.helpers.recycle_bin import restored_domain
from rethinkdb import r

RETHINKDB_ADDRESS = os.environ.get("ISARD_TEST_RETHINKDB", "")

pytestmark = pytest.mark.skipif(
    not RETHINKDB_ADDRESS, reason="ISARD_TEST_RETHINKDB is unset"
)


@pytest.fixture
def conn():
    host, _, port = RETHINKDB_ADDRESS.partition(":")
    c = r.connect(host=host, port=int(port or 28015))
    yield c
    c.close()


@pytest.mark.parametrize(
    "status, expected",
    [
        ("CreatingDisk", "Stopped"),
        ("CreatingDomain", "Stopped"),
        ("Starting", "Stopped"),
        ("Started", "Stopped"),
        ("Stopped", "Stopped"),
        ("Failed", "Failed"),
        (None, "Stopped"),
    ],
)
def test_a_restored_domain_is_at_rest(conn, status, expected):
    doc = {"id": "d1", "parents": ["t1", None], "xml_to_start": "<domain/>"}
    if status is not None:
        doc["status"] = status
    row = r.expr([doc]).map(restored_domain).nth(0).run(conn)
    assert row["status"] == expected
    assert row["parents"] == ["t1"]
    assert "xml_to_start" not in row
