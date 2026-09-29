# SPDX-License-Identifier: AGPL-3.0-or-later

"""A purge claims only an entry it may still purge; a restored one is never taken back."""

import os
import uuid

import pytest
from isardvdi_common.helpers.recycle_bin import Helpers
from rethinkdb import r

RETHINKDB_ADDRESS = os.environ.get("ISARD_TEST_RETHINKDB", "")

pytestmark = pytest.mark.skipif(
    not RETHINKDB_ADDRESS, reason="ISARD_TEST_RETHINKDB is unset"
)


@pytest.fixture
def entries():
    host, _, port = RETHINKDB_ADDRESS.partition(":")
    conn = r.connect(host=host, port=int(port or 28015))
    name = f"recycle_bin_{uuid.uuid4().hex[:10]}"
    r.db_create(name).run(conn)
    r.db(name).table_create("recycle_bin").run(conn)
    yield r.db(name).table("recycle_bin"), conn
    r.db_drop(name).run(conn)
    conn.close()


@pytest.mark.parametrize(
    "status, after",
    [
        ("recycled", "queued"),
        ("queued", "queued"),
        ("deleting", "queued"),
        ("restored", "restored"),
        ("deleted", "deleted"),
    ],
)
def test_a_purge_claims_only_an_entry_it_may_purge(entries, status, after):
    table, conn = entries
    table.insert({"id": "rb-1", "status": status}).run(conn)
    table.get("rb-1").update(Helpers.purge_claim()).run(conn)
    assert table.get("rb-1")["status"].run(conn) == after
