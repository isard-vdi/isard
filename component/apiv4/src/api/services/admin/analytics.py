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

from isardvdi_common.lib.analytics.analytics import AnalyticsProcessed


class AdminAnalyticsService:
    """Thin facade over AnalyticsProcessed.

    Method names are pinned by ``api/routes/tests/test_admin_analytics.py``
    monkeypatches; keep them stable.
    """

    # =========================================================================
    # STORAGE & RESOURCE ANALYTICS
    # =========================================================================

    @staticmethod
    def storage_usage(categories=None):
        return AnalyticsProcessed.storage_usage(categories)

    @staticmethod
    def resource_count(categories=None):
        return AnalyticsProcessed.resource_count(categories)

    @staticmethod
    def suggested_removals(categories=None, months_without_use=6):
        return AnalyticsProcessed.suggested_removals(categories, months_without_use)

    # =========================================================================
    # GRAPH CONFIGURATION
    # =========================================================================

    @staticmethod
    def get_usage_graphs_conf():
        return AnalyticsProcessed.list_graph_configs()

    @staticmethod
    def get_usage_graph_conf(graph_conf_id):
        return AnalyticsProcessed.get_graph_config(graph_conf_id)

    @staticmethod
    def add_usage_graph_conf(data):
        AnalyticsProcessed.create_graph_config(data)

    @staticmethod
    def update_usage_graph_conf(graph_conf_id, data):
        AnalyticsProcessed.update_graph_config(graph_conf_id, data)

    @staticmethod
    def delete_usage_graph_conf(graph_conf_id):
        AnalyticsProcessed.delete_graph_config(graph_conf_id)

    # =========================================================================
    # DESKTOP ANALYTICS
    # =========================================================================

    @staticmethod
    def get_desktops_less_used(
        days_before=30, limit=None, not_in_directory_path=None, status=False
    ):
        return AnalyticsProcessed.get_desktops_less_used(
            days_before, limit, not_in_directory_path, status
        )

    @staticmethod
    def get_desktops_recently_used(
        days_before=30, limit=None, not_in_directory_path=None, status=False
    ):
        return AnalyticsProcessed.get_desktops_recently_used(
            days_before, limit, not_in_directory_path, status
        )

    @staticmethod
    def get_desktops_most_used(
        days_before=7, limit=None, not_in_directory_path=None, status=False
    ):
        return AnalyticsProcessed.get_desktops_most_used(
            days_before, limit, not_in_directory_path, status
        )

    # =========================================================================
    # ECHART DATA
    # =========================================================================

    @staticmethod
    def get_daily_items(table, date_field):
        return AnalyticsProcessed.get_daily_items(table, date_field)

    @staticmethod
    def get_grouped_data(table, field):
        return AnalyticsProcessed.get_grouped_data(table, field)

    @staticmethod
    def get_grouped_unique_data(table, field, unique_field):
        return AnalyticsProcessed.get_grouped_unique_data(table, field, unique_field)

    @staticmethod
    def get_nested_array_grouped_data(table, array_field, field):
        return AnalyticsProcessed.get_nested_array_grouped_data(
            table, array_field, field
        )
