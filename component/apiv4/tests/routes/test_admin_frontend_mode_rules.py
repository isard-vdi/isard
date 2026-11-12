#
#   Copyright © 2026 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from uuid import UUID

import pytest
from isardvdi_common.helpers.caches import Caches
from rethinkdb import r
from rethinkdb_mock import MockThink
from tests.routes.helpers import MockJWT

URL = "/items/frontend-mode-rules"
CREATE_URL = "/item/frontend-mode-rule"

NO_ALLOWED = {"categories": False, "groups": False, "roles": False, "users": False}


def _rule(rule_id, priority, frontend_mode="actual"):
    return {
        "id": rule_id,
        "name": f"Rule {rule_id}",
        "description": "",
        "priority": priority,
        "allowed": NO_ALLOWED,
        "frontend_mode": frontend_mode,
    }


def test_admin_lists_rules_ordered_by_priority(test_client):
    """The query runs against the table, so the highest priority comes first."""
    response = test_client(
        url=URL,
        jwt=MockJWT(role_id="admin"),
        db_tables_data={
            "frontend_mode_rules": [
                _rule("low", 1, "deprecated"),
                _rule("high", 10, "actual"),
                _rule("mid", 5, "all"),
            ]
        },
    )

    assert response.status_code == 200
    rules = response.json()["rules"]
    assert [r["id"] for r in rules] == ["high", "mid", "low"]
    assert rules[0] == _rule("high", 10, "actual")


def test_admin_lists_no_rules_when_table_is_empty(test_client):
    response = test_client(
        url=URL,
        jwt=MockJWT(role_id="admin"),
        db_tables_data={"frontend_mode_rules": []},
    )

    assert response.status_code == 200
    assert response.json() == {"rules": []}


@pytest.mark.parametrize("role_id", ["manager", "advanced", "user"])
def test_non_admin_roles_cannot_list_rules(monkeypatch, test_client, role_id):
    called = False

    def fake_get_all():
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(
        "api.routes.admin.frontend_mode_rules.AdminFrontendModeRulesService"
        ".get_all_frontend_mode_rules",
        staticmethod(fake_get_all),
    )

    response = test_client(url=URL, jwt=MockJWT(role_id=role_id))

    assert response.status_code == 403
    assert not called


@pytest.fixture
def rules_conn():
    tables = {
        "config": [{"id": 1, "maintenance": False}],
        "categories": [{"id": "default"}],
        "frontend_mode_rules": [],
    }
    mock_db = MockThink({"dbs": {"isard": {"tables": tables}}, "default": "isard"})
    with mock_db.connect() as conn:
        yield conn


@pytest.fixture
def post_rule(test_client_with_conn, rules_conn):
    def post(body, jwt=None):
        return test_client_with_conn(
            db_tables_data={},
            conn=rules_conn,
            url=CREATE_URL,
            method="POST",
            body=body,
            jwt=jwt or MockJWT(role_id="admin"),
        )

    return post


def _create_body(**overrides):
    return {
        "name": "Teachers",
        "description": "Teachers try the new frontend",
        "priority": 10,
        "allowed": NO_ALLOWED,
        "frontend_mode": "actual",
        **overrides,
    }


def _stored_rules(conn):
    return list(r.table("frontend_mode_rules").run(conn))


def _the_only_stored_rule(conn):
    rules = _stored_rules(conn)
    assert len(rules) == 1
    return rules[0]


def test_created_rule_is_stored_with_the_posted_fields(post_rule, rules_conn):
    body = {
        "name": "Teachers",
        "description": "Teachers try the new frontend",
        "priority": 10,
        "allowed": {
            "categories": False,
            "groups": False,
            "roles": ["teacher"],
            "users": False,
        },
        "frontend_mode": "hidden",
    }

    response = post_rule(body)

    assert response.status_code == 204
    assert response.content == b""
    stored = _the_only_stored_rule(rules_conn)
    assert stored == {**body, "id": stored["id"]}


def test_created_rule_gets_a_server_generated_uuid4_id(post_rule, rules_conn):
    post_rule(_create_body())

    stored = _the_only_stored_rule(rules_conn)

    assert UUID(stored["id"]).version == 4


def test_created_rule_ignores_an_id_sent_by_the_client(post_rule, rules_conn):
    response = post_rule(_create_body(id="my-rule"))

    assert response.status_code == 204
    assert _the_only_stored_rule(rules_conn)["id"] != "my-rule"


def test_each_created_rule_gets_its_own_id(post_rule, rules_conn):
    post_rule(_create_body(name="First", priority=1))

    post_rule(_create_body(name="Second", priority=2))

    first, second = _stored_rules(rules_conn)
    assert first["id"] != second["id"]


def test_created_rule_description_is_empty_when_omitted(post_rule, rules_conn):
    response = post_rule(
        {
            "name": "No description",
            "priority": 1,
            "allowed": NO_ALLOWED,
            "frontend_mode": "all",
        }
    )

    assert response.status_code == 204
    assert _the_only_stored_rule(rules_conn)["description"] == ""


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"priority": 1, "allowed": NO_ALLOWED, "frontend_mode": "actual"},
            id="missing-name",
        ),
        pytest.param(
            {
                "name": "x" * 51,
                "priority": 1,
                "allowed": NO_ALLOWED,
                "frontend_mode": "actual",
            },
            id="name-over-50-chars",
        ),
        pytest.param(
            {
                "name": "Beta",
                "priority": 1,
                "allowed": NO_ALLOWED,
                "frontend_mode": "beta",
            },
            id="unknown-frontend-mode",
        ),
        pytest.param(
            {"name": "No priority", "allowed": NO_ALLOWED, "frontend_mode": "actual"},
            id="missing-priority",
        ),
    ],
)
def test_invalid_rule_is_rejected_without_storing_anything(post_rule, rules_conn, body):
    response = post_rule(body)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert _stored_rules(rules_conn) == []


@pytest.mark.parametrize("role_id", ["manager", "advanced", "user"])
def test_non_admin_roles_cannot_create_rules(post_rule, rules_conn, role_id):
    response = post_rule(_create_body(), jwt=MockJWT(role_id=role_id))

    assert response.status_code == 403
    assert _stored_rules(rules_conn) == []


def test_creating_a_rule_with_a_taken_priority_is_refused(post_rule, rules_conn):
    r.table("frontend_mode_rules").insert(_rule("rule-1", 5)).run(rules_conn)

    response = post_rule(_create_body(priority=5))

    assert response.status_code == 409
    assert response.json()["error"] == "conflict"
    assert _stored_rules(rules_conn) == [_rule("rule-1", 5)]


@pytest.mark.clear_cache
def test_cached_rules_include_a_rule_created_after_they_were_cached(post_rule):
    post_rule(_create_body(name="First", priority=1))
    Caches.get_cached_frontend_mode_rules()

    post_rule(_create_body(name="Second", priority=2))

    cached = Caches.get_cached_frontend_mode_rules()
    assert len(cached) == 2
    assert cached[0]["name"] == "Second"
