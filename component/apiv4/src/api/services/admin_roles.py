#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

from api.services.error import Error
from isardvdi_common.models.roles import Roles


class AdminRolesService:
    """Service for admin roles management."""

    @staticmethod
    def get_roles() -> list:
        """Get all roles."""
        return Roles.get_all()

    @staticmethod
    def get_role(role_id: str) -> dict:
        """Get a single role by ID."""
        role = Roles.get(role_id)
        if not role:
            raise Error("not_found", "Role not found")
        return role
