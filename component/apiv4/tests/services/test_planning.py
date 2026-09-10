# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``PlanningService`` — pins the Bug 35 remediation.

Bug 35 (load-testing rev 8): ``DELETE /api/v4/item/planning/{nonexistent_uuid}``
returned 500 with the inner Error tuple stringified into the message
(``Failed to delete planning <id>: ('not_found', 'Plan not found …')``).
Root cause was a bare ``except Exception`` block in
``services/planning.py`` that caught the inner
``Error("not_found", …)`` raised by ``ReservablesPlannerProccess.delete_plan``
and re-wrapped it as ``Error("internal_server", …)``.

The fix adds ``except Error: raise`` before ``except Exception`` so
typed errors propagate to the route layer and surface with their
real status code (404). Same pattern as Bug 14/15 family.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.planning import PlanningService

# An admin payload makes the per-category ownership guards a no-op (admins are
# unrestricted), so these tests exercise the downstream error handling only.
_ADMIN = {"role_id": "admin", "category_id": "*", "user_id": "admin"}


class TestDeletePlanning:
    """Pins Bug 35 — the typed Error must propagate, not be re-wrapped."""

    def test_typed_error_propagates_unchanged(self):
        """A ``not_found`` from ``delete_plan`` must surface as
        ``not_found``, NOT a generic ``internal_server``."""
        with patch(
            "api.services.planning.ReservablesPlannerProccess.delete_plan",
            side_effect=Error("not_found", "Plan not found. Could not be deleted"),
        ):
            with pytest.raises(Error) as exc_info:
                PlanningService.delete_planning(_ADMIN, "nonexistent-uuid")

        # The error_type / status are encoded as the first arg of Error.
        # Before the fix this would be "internal_server" because the bare
        # ``except Exception`` wrapped the inner Error.
        assert exc_info.value.args[0] == "not_found"
        assert "Plan not found" in exc_info.value.args[1]
        # And critically, the message is the original — NOT a string-
        # formatted Error tuple like
        # "Failed to delete planning …: ('not_found', 'Plan not found')"
        # (which is exactly the symptom the bug doc captured).
        assert "Failed to delete planning" not in exc_info.value.args[1]

    def test_unexpected_exception_still_becomes_internal_server(self):
        """Unrelated exceptions are still wrapped as 500. The fix only
        unblocks typed Errors; non-Error exceptions keep going through
        the generic handler so callers get a sanitised 500 instead of
        the raw traceback leaking out."""
        with patch(
            "api.services.planning.ReservablesPlannerProccess.delete_plan",
            side_effect=RuntimeError("rdb pool exhausted"),
        ):
            with pytest.raises(Error) as exc_info:
                PlanningService.delete_planning(_ADMIN, "any-id")

        assert exc_info.value.args[0] == "internal_server"
        assert "Failed to delete planning" in exc_info.value.args[1]


class TestGetItemPlannings:
    """Same except-Error: raise gate applies on the read side too."""

    def test_typed_error_propagates_unchanged(self):
        with patch(
            "api.services.planning.ReservablesPlannerProccess.list_item_plans",
            side_effect=Error("forbidden", "Item belongs to another category"),
        ):
            with pytest.raises(Error) as exc_info:
                PlanningService.get_item_plannings(_ADMIN, "item-x")

        assert exc_info.value.args[0] == "forbidden"
        assert "Item belongs to another category" in exc_info.value.args[1]

    def test_unexpected_exception_still_becomes_internal_server(self):
        with patch(
            "api.services.planning.ReservablesPlannerProccess.list_item_plans",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(Error) as exc_info:
                PlanningService.get_item_plannings(_ADMIN, "item-x")

        assert exc_info.value.args[0] == "internal_server"
        assert "Failed to retrieve plannings" in exc_info.value.args[1]


class TestPerCategoryOwnershipGuards:
    """Pins the port gap: the planner endpoints must invoke the per-card
    ownership guards (the helpers exist in the _common twin but the apiv4
    create/delete/get paths previously never called them, so a manager could
    create/delete/read plannings on cards delegated to another category by id).
    A manager payload whose card is not delegated to them must be rejected
    BEFORE the planner mutation runs."""

    _MANAGER = {"role_id": "manager", "category_id": "cat-1", "user_id": "u1"}

    def test_create_rejects_unowned_card_before_add(self):
        with patch(
            "api.services.planning.ReservablesPlannerProccess._assert_manager_owns_card",
            side_effect=Error(
                "forbidden", "GPU card is not delegated to your category"
            ),
        ), patch(
            "api.services.planning.ReservablesPlannerProccess.add_plan"
        ) as add_plan:
            with pytest.raises(Error) as exc_info:
                PlanningService.create_planning(
                    self._MANAGER,
                    {"item_id": "card-other", "item_type": "gpus", "subitem_id": "p"},
                )
        assert exc_info.value.args[0] == "forbidden"
        add_plan.assert_not_called()

    def test_delete_rejects_unowned_plan_before_delete(self):
        with patch(
            "api.services.planning.ReservablesPlannerProccess._assert_manager_owns_plan",
            side_effect=Error("not_found", "Plan not found"),
        ), patch(
            "api.services.planning.ReservablesPlannerProccess.delete_plan"
        ) as delete_plan:
            with pytest.raises(Error) as exc_info:
                PlanningService.delete_planning(self._MANAGER, "plan-other")
        assert exc_info.value.args[0] == "not_found"
        delete_plan.assert_not_called()

    def test_get_rejects_unowned_card_before_list(self):
        with patch(
            "api.services.planning.ReservablesPlannerProccess._assert_manager_owns_card",
            side_effect=Error(
                "forbidden", "GPU card is not delegated to your category"
            ),
        ), patch(
            "api.services.planning.ReservablesPlannerProccess.list_item_plans"
        ) as list_item_plans:
            with pytest.raises(Error) as exc_info:
                PlanningService.get_item_plannings(self._MANAGER, "card-other")
        assert exc_info.value.args[0] == "forbidden"
        list_item_plans.assert_not_called()
