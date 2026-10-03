# SPDX-License-Identifier: AGPL-3.0-or-later

"""Putting a recycle-bin entry back to ``recycled`` after a failed delete, on a real RethinkDB.

The failure handler runs after the cascade of another entry may already have deleted (or a
restore restored) this one, so the write must not overwrite a terminal status. That is the
server's ``r.branch`` inside the update, which a mocked connection cannot show.
"""

from __future__ import annotations

import os
import uuid

import pytest

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real


@pytest.fixture
def conn():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    try:
        c = r.connect(
            host=host, port=int(os.environ.get("RETHINKDB_PORT", "28015")), db="isard"
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}: {exc}")
    yield c
    c.close()


@pytest.fixture
def entry(conn):
    ids = []

    def make(status):
        rb_id = f"e2e-rb-{uuid.uuid4()}"
        r.table("recycle_bin").insert({"id": rb_id, "status": status}).run(conn)
        ids.append(rb_id)
        return rb_id

    yield make
    r.table("recycle_bin").get_all(*ids).delete().run(conn)


@pytest.mark.parametrize(
    "status, expected",
    [
        ("queued", "recycled"),
        ("deleting", "recycled"),
        ("deleted", "deleted"),
        ("restored", "restored"),
    ],
)
def test_revert_to_recycled_keeps_a_terminal_status(conn, entry, status, expected):
    from isardvdi_common.helpers.recycle_bin import Helpers

    rb_id = entry(status)
    Helpers.revert_to_recycled(rb_id)

    assert r.table("recycle_bin").get(rb_id)["status"].run(conn) == expected
