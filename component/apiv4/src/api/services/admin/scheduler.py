#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from isardvdi_common.lib.api_admin import ApiAdmin


class AdminSchedulerService:

    @staticmethod
    def get_system_jobs() -> list:
        """Get system scheduler jobs filtered by type 'system'."""
        return ApiAdmin.admin_table_list(
            "scheduler_jobs",
            order_by="next_run_time",
            pluck=["id", "name", "kind", "next_run_time"],
            id="system",
            index="type",
        )

    @staticmethod
    def get_bookings_jobs() -> list:
        """Get bookings scheduler jobs filtered by type 'bookings'."""
        return ApiAdmin.admin_table_list(
            "scheduler_jobs",
            order_by="next_run_time",
            pluck=["id", "name", "kind", "next_run_time", "kwargs"],
            id="bookings",
            index="type",
        )
