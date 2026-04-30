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

from isardvdi_common.lib.stats.stats import StatsProcessed


class AdminStatsService:
    """Service for system statistics.

    Thin façade over ``StatsProcessed``. The method names are pinned by
    ``api/routes/tests/test_admin_stats.py`` monkeypatches; keep them
    stable.
    """

    @staticmethod
    def get_users_stats():
        return StatsProcessed.get_users_stats()

    @staticmethod
    def get_desktops_stats():
        return StatsProcessed.get_desktops_stats()

    @staticmethod
    def get_templates_stats():
        return StatsProcessed.get_templates_stats()

    @staticmethod
    def get_general_stats():
        return StatsProcessed.get_general_stats()

    @staticmethod
    def get_domains_status():
        return StatsProcessed.get_domains_status()

    @staticmethod
    def get_kind(kind):
        return StatsProcessed.get_kind(kind)

    @staticmethod
    def get_category_status():
        return StatsProcessed.get_category_status()

    @staticmethod
    def get_group_by_categories():
        return StatsProcessed.get_group_by_categories()

    @staticmethod
    def get_categories_kind_state(kind, state=False):
        return StatsProcessed.get_categories_kind_state(kind, state)

    @staticmethod
    def get_categories_limits_hardware():
        return StatsProcessed.get_categories_limits_hardware()

    @staticmethod
    def get_categories_deployments():
        return StatsProcessed.get_categories_deployments()

    @staticmethod
    def get_domains_by_category_count():
        return StatsProcessed.get_domains_by_category_count()
