#
#   Copyright © 2026 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from tests.routes.helpers import MockJWT

URL = "/items/frontend-mode-rules"

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
