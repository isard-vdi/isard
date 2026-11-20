#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Adrià Garriga Bassas
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from api.services.error import Error
from fastapi import BackgroundTasks
from isardvdi_common.lib.domains.desktops.desktops_nonpersistent import (
    DesktopsNonpersistentProcessed as CommonDesktopsNonpersistent,
)
from isardvdi_common.models.frontend_mode_rules import FrontendModeRules


class AdminFrontendModeRulesService:
    """Service for admin frontend mode rules management"""

    @staticmethod
    def get_all_frontend_mode_rules() -> list[dict]:
        return FrontendModeRules.get_all_ordered_by_priority()

    @staticmethod
    def get_frontend_mode_rule(rule_id: str) -> dict:
        rule = FrontendModeRules.get(rule_id)

        if not rule:
            raise Error("not_found", f"Frontend mode rule with ID {rule_id} not found")

        return rule

    @staticmethod
    def create_frontend_mode_rule(
        data: dict, background_tasks: BackgroundTasks
    ) -> None:
        """Create a new frontend mode rule with a server-generated id."""
        FrontendModeRules.create(data)
        AdminFrontendModeRulesService.schedule_temporal_cleanup(background_tasks)

    @staticmethod
    def update_frontend_mode_rule(
        rule_id: str, data: dict, background_tasks: BackgroundTasks
    ) -> None:
        """Update the given fields of a frontend mode rule."""
        FrontendModeRules.update(rule_id, data)
        AdminFrontendModeRulesService.schedule_temporal_cleanup(background_tasks)

    @staticmethod
    def delete_frontend_mode_rule(
        rule_id: str, background_tasks: BackgroundTasks
    ) -> None:
        """Delete a frontend mode rule."""
        FrontendModeRules.delete(rule_id)
        AdminFrontendModeRulesService.schedule_temporal_cleanup(background_tasks)

    @staticmethod
    def schedule_temporal_cleanup(background_tasks: BackgroundTasks) -> None:
        """Any rule change can take users off the ``actual`` frontend mode, the
        only one allowing several temporals per template: once the response is
        out, delete the temporals of every template they hold several of."""
        # TODO(old-frontend-removal): goes with the one-per-template rule.

        background_tasks.add_task(
            CommonDesktopsNonpersistent.enforce_single_temporal_per_template
        )
