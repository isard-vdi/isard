#
#   Copyright © 2026 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from uuid import UUID

import pytest
from isardvdi_common.helpers.caches import Caches
from rethinkdb import r
from rethinkdb_mock import MockThink
from tests.routes.helpers import MockJWT, create_indexes

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
        "categories": [{"id": "default", "name": "Default"}],
        "frontend_mode_rules": [],
        # What the temporal cleanup each rule change schedules reads.
        "domains": [],
        "groups": [{"id": "default-default", "name": "Default"}],
        "roles": [{"id": "user", "name": "User"}],
        "users": [],
    }
    mock_db = MockThink({"dbs": {"isard": {"tables": tables}}, "default": "isard"})
    with mock_db.connect() as conn:
        create_indexes({"domains": []}, conn)
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


@pytest.fixture
def put_rule(test_client_with_conn, rules_conn):
    def put(rule_id, body, jwt=None):
        return test_client_with_conn(
            db_tables_data={},
            conn=rules_conn,
            url=f"/item/frontend-mode-rule/{rule_id}",
            method="PUT",
            body=body,
            jwt=jwt or MockJWT(role_id="admin"),
        )

    return put


def _seed(conn, *rules):
    r.table("frontend_mode_rules").insert(list(rules)).run(conn)


def _stored_rule(conn, rule_id):
    return r.table("frontend_mode_rules").get(rule_id).run(conn)


def test_edited_rule_changes_only_the_sent_fields(put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1, "deprecated"))

    response = put_rule("rule-1", {"priority": 7})

    assert response.status_code == 204
    assert response.content == b""
    assert _stored_rule(rules_conn, "rule-1") == {
        **_rule("rule-1", 1, "deprecated"),
        "priority": 7,
    }


def test_edited_rule_replaces_allowed_as_a_whole(put_rule, rules_conn):
    _seed(
        rules_conn,
        {
            **_rule("rule-1", 1),
            "allowed": {
                "categories": ["default"],
                "groups": False,
                "roles": ["admin"],
                "users": False,
            },
        },
    )

    put_rule("rule-1", {"allowed": {"groups": ["g1"]}})

    assert _stored_rule(rules_conn, "rule-1")["allowed"] == {
        "categories": False,
        "groups": ["g1"],
        "roles": False,
        "users": False,
    }


def test_editing_a_rule_leaves_the_other_rules_untouched(put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1), _rule("rule-2", 2))

    put_rule("rule-1", {"name": "Renamed"})

    assert _stored_rule(rules_conn, "rule-2") == _rule("rule-2", 2)


def test_editing_an_unknown_rule_is_not_found(monkeypatch, put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1))
    # rethinkdb_mock can't evaluate `.default()` on a missing row, so `exists` raises there
    monkeypatch.setattr(
        "isardvdi_common.models.frontend_mode_rules.FrontendModeRules.exists",
        staticmethod(lambda rule_id: False),
    )

    response = put_rule("missing", {"priority": 7})

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert _stored_rules(rules_conn) == [_rule("rule-1", 1)]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"name": "x" * 51}, id="name-over-50-chars"),
        pytest.param({"description": "x" * 256}, id="description-over-255-chars"),
        pytest.param({"frontend_mode": "beta"}, id="unknown-frontend-mode"),
        pytest.param({"priority": "high"}, id="priority-not-a-number"),
    ],
)
def test_invalid_edit_is_rejected_without_changing_the_rule(put_rule, rules_conn, body):
    _seed(rules_conn, _rule("rule-1", 1))

    response = put_rule("rule-1", body)

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"
    assert _stored_rule(rules_conn, "rule-1") == _rule("rule-1", 1)


@pytest.mark.parametrize("role_id", ["manager", "advanced", "user"])
def test_non_admin_roles_cannot_edit_rules(put_rule, rules_conn, role_id):
    _seed(rules_conn, _rule("rule-1", 1))

    response = put_rule("rule-1", {"priority": 7}, jwt=MockJWT(role_id=role_id))

    assert response.status_code == 403
    assert _stored_rule(rules_conn, "rule-1") == _rule("rule-1", 1)


@pytest.mark.clear_cache
def test_cached_rules_reflect_an_edit(put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1))
    put_rule("rule-1", {"name": "Before"})
    Caches.get_cached_frontend_mode_rules()

    put_rule("rule-1", {"name": "After"})

    assert Caches.get_cached_frontend_mode_rules()[0]["name"] == "After"


def test_editing_a_rule_to_a_taken_priority_is_refused(put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1), _rule("rule-2", 2))

    response = put_rule("rule-1", {"priority": 2})

    assert response.status_code == 409
    assert response.json()["error"] == "conflict"
    assert _stored_rule(rules_conn, "rule-1") == _rule("rule-1", 1)
    assert _stored_rule(rules_conn, "rule-2") == _rule("rule-2", 2)


def test_edited_rule_can_keep_its_own_priority(put_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1))

    response = put_rule("rule-1", {"priority": 1, "name": "Renamed"})

    assert response.status_code == 204
    assert _stored_rule(rules_conn, "rule-1")["name"] == "Renamed"


@pytest.fixture
def delete_rule(test_client_with_conn, rules_conn):
    def delete(rule_id, jwt=None):
        return test_client_with_conn(
            db_tables_data={},
            conn=rules_conn,
            url=f"/item/frontend-mode-rule/{rule_id}",
            method="DELETE",
            jwt=jwt or MockJWT(role_id="admin"),
        )

    return delete


def test_deleted_rule_is_removed_and_others_kept(delete_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1), _rule("rule-2", 2))

    response = delete_rule("rule-1")

    assert response.status_code == 204
    assert response.content == b""
    assert _stored_rules(rules_conn) == [_rule("rule-2", 2)]


def test_deleting_an_unknown_rule_is_not_found(monkeypatch, delete_rule, rules_conn):
    _seed(rules_conn, _rule("rule-1", 1))
    # rethinkdb_mock can't `.delete()` a missing row; real RethinkDB reports 0 deleted
    monkeypatch.setattr(
        "isardvdi_common.connections.rethink_base.RethinkBase.delete",
        classmethod(lambda cls, rule_id: False),
    )

    response = delete_rule("missing")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert _stored_rules(rules_conn) == [_rule("rule-1", 1)]


@pytest.mark.parametrize("role_id", ["manager", "advanced", "user"])
def test_non_admin_roles_cannot_delete_rules(delete_rule, rules_conn, role_id):
    _seed(rules_conn, _rule("rule-1", 1))

    response = delete_rule("rule-1", jwt=MockJWT(role_id=role_id))

    assert response.status_code == 403
    assert _stored_rules(rules_conn) == [_rule("rule-1", 1)]


@pytest.mark.clear_cache
def test_cached_rules_drop_a_deleted_rule(delete_rule, rules_conn):
    _seed(rules_conn, _rule("rule-0", 0), _rule("rule-1", 1), _rule("rule-2", 2))
    delete_rule("rule-0")
    Caches.get_cached_frontend_mode_rules()

    delete_rule("rule-1")

    assert [r["id"] for r in Caches.get_cached_frontend_mode_rules()] == ["rule-2"]


# ─── Leaving ``actual`` deletes the temporals of a template held twice ──
# TODO(old-frontend-removal): the whole section goes with that rule.


def _seed_user_with_temporals(conn):
    """``u-1`` holds two temporals of ``t-1``, one of ``t-2`` and a persistent
    desktop of ``t-1``."""
    r.table("users").insert(
        {
            "id": "u-1",
            "provider": "local",
            "name": "User One",
            "uid": "u1",
            "username": "u1",
            "role": "user",
            "category": "default",
            "group": "default-default",
        }
    ).run(conn)
    r.table("domains").insert(
        [
            _desktop("d-1", "t-1", persistent=False),
            _desktop("d-2", "t-1", persistent=False),
            _desktop("d-3", "t-2", persistent=False),
            _desktop("d-4", "t-1", persistent=True),
        ]
    ).run(conn)


def _desktop(desktop_id, template_id, persistent):
    return {
        "id": desktop_id,
        "kind": "desktop",
        "user": "u-1",
        "from_template": template_id,
        "persistent": persistent,
        "status": "Started",
    }


@pytest.fixture
def deleted(monkeypatch):
    """The (user, template) pairs whose temporals the cleanup deletes.

    rethinkdb_mock can't run the delete itself (``get_field`` over a
    selection), and it is covered on its own."""
    pairs = []
    monkeypatch.setattr(
        "isardvdi_common.lib.domains.desktops.desktops_nonpersistent"
        ".DesktopNonpersistentEvents.desktops_non_persistent_delete",
        classmethod(lambda cls, user_id, template: pairs.append((user_id, template))),
    )
    return pairs


_USER_ONE_ONLY = {**NO_ALLOWED, "users": ["u-1"]}


@pytest.mark.clear_cache
def test_deleting_the_rule_keeping_a_user_on_actual_deletes_their_extra_temporals(
    monkeypatch, delete_rule, rules_conn, deleted
):
    monkeypatch.setenv("FRONTEND_MODE", "all")
    _seed(rules_conn, {**_rule("rule-1", 1, "actual"), "allowed": _USER_ONE_ONLY})
    _seed_user_with_temporals(rules_conn)

    response = delete_rule("rule-1")

    assert response.status_code == 204
    assert deleted == [("u-1", "t-1")]


@pytest.mark.clear_cache
def test_editing_a_rule_off_actual_deletes_the_extra_temporals(
    monkeypatch, put_rule, rules_conn, deleted
):
    monkeypatch.setenv("FRONTEND_MODE", "actual")
    _seed(rules_conn, {**_rule("rule-1", 1, "actual"), "allowed": _USER_ONE_ONLY})
    _seed_user_with_temporals(rules_conn)

    response = put_rule("rule-1", {"frontend_mode": "deprecated"})

    assert response.status_code == 204
    assert deleted == [("u-1", "t-1")]


@pytest.mark.clear_cache
def test_a_higher_rule_off_actual_deletes_the_extra_temporals(
    monkeypatch, post_rule, rules_conn, deleted
):
    monkeypatch.setenv("FRONTEND_MODE", "actual")
    _seed_user_with_temporals(rules_conn)

    response = post_rule(
        _create_body(priority=10, frontend_mode="hidden", allowed=_USER_ONE_ONLY)
    )

    assert response.status_code == 204
    assert deleted == [("u-1", "t-1")]


@pytest.mark.clear_cache
def test_a_rule_change_that_leaves_the_user_on_actual_deletes_nothing(
    monkeypatch, post_rule, rules_conn, deleted
):
    monkeypatch.setenv("FRONTEND_MODE", "actual")
    _seed_user_with_temporals(rules_conn)

    response = post_rule(
        _create_body(
            frontend_mode="deprecated",
            allowed={**NO_ALLOWED, "users": ["someone-else"]},
        )
    )

    assert response.status_code == 204
    assert deleted == []


@pytest.mark.clear_cache
def test_a_refused_rule_change_deletes_nothing(
    monkeypatch, post_rule, rules_conn, deleted
):
    """Even a user already off ``actual`` keeps their temporals until a rule
    actually changes."""
    monkeypatch.setenv("FRONTEND_MODE", "all")
    _seed(rules_conn, _rule("rule-1", 1, "deprecated"))
    _seed_user_with_temporals(rules_conn)

    response = post_rule(_create_body(priority=1))

    assert response.status_code == 409
    assert deleted == []
