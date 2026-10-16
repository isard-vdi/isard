# SPDX-License-Identifier: AGPL-3.0-or-later

"""What a participant sees of a deployment once visibility is per desktop.

The deployment's ``tag_visible`` is only the OR over every user's desktops,
so the fixture has another user's visible desktop keeping that flag up.
"""

import asyncio
import contextlib

import pytest
from api.dependencies import alloweds
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed,
)
from rethinkdb import r
from rethinkdb_mock import MockThink


def _desktop(id, user, visible):
    return {
        "id": id,
        "kind": "desktop",
        "user": user,
        "tag": "dep-1",
        "tag_visible": visible,
        "name": id,
    }


@pytest.fixture()
def db(monkeypatch):
    mock_db = MockThink(
        {
            "dbs": {
                "isard": {
                    "tables": {
                        "domains": [
                            _desktop("u1-a", "u1", False),
                            _desktop("u1-b", "u1", False),
                            _desktop("u2-a", "u2", True),
                            _desktop("u2-b", "u2", False),
                        ],
                    }
                }
            },
            "default": "isard",
        }
    )
    with mock_db.connect() as conn:
        r.table("domains").index_create("tag").run(conn)
        r.table("domains").index_create(
            "kind_user_tag", [r.row["kind"], r.row["user"], r.row["tag"]]
        ).run(conn)
        r.table("domains").index_wait().run(conn)
        monkeypatch.setattr(
            "isardvdi_common.connections.rethink_shared_connection.RethinkSharedConnection._rdb_context",
            contextlib.nullcontext,
        )
        monkeypatch.setattr(
            "isardvdi_common.connections.rethink_shared_connection.RethinkSharedConnection._rdb_connection",
            conn,
        )
        yield conn


def test_user_has_visible_desktops_looks_at_that_user_only(db):
    assert DeploymentDesktopsProcessed.user_has_visible_desktops("dep-1", "u1") is False
    assert DeploymentDesktopsProcessed.user_has_visible_desktops("dep-1", "u2") is True


@pytest.mark.parametrize(
    "requester, manages, expected",
    [
        ("u2", False, True),  # the participant themselves
        ("u2", True, False),  # an owner who also has desktops in it
        ("owner", True, False),  # the owner looking at the participant
    ],
)
def test_only_the_participant_is_limited_to_visible(
    monkeypatch, requester, manages, expected
):
    monkeypatch.setattr(alloweds, "_manages_deployment", lambda *_: manages)
    only_visible = asyncio.run(
        alloweds.deployment_user_sees_only_visible(
            payload={"user_id": requester}, deployment_id="dep-1", user_id="u2"
        )
    )
    assert only_visible is expected
