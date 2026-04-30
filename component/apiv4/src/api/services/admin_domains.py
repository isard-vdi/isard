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

import json
import logging as log
import traceback

from api.services.error import Error
from api.services.templates import clear_templates_cache
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.helpers.api_notify import notify_admin, notify_admins
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.lib.domains.domains import DomainsProcessed
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.storage import Storage
from rethinkdb import r

domains_field_cache = TTLCache(maxsize=50, ttl=5)


def clear_domains_field_cache():
    domains_field_cache.clear()


class AdminDomainsService:
    """
    Service for admin domain management operations.
    """

    # ── Ownership Checks ─────────────────────────────────────────────────

    @staticmethod
    def owns_domain_id(payload, domain_id):
        """Check if the admin/manager owns the domain."""
        Helpers.owns_domain_id(payload, domain_id)

    # ── List Domains ─────────────────────────────────────────────────────

    @staticmethod
    def list_desktops(payload, categories=None):
        """List desktops, optionally filtered by categories."""
        if payload["role_id"] == "manager":
            categories = [payload["category_id"]]
        elif categories:
            categories = (
                json.loads(categories) if isinstance(categories, str) else categories
            )
        return ApiAdmin.ListDesktops(categories)

    @staticmethod
    def get_domains_by_ids(payload, domain_ids):
        """Get specific domains by ID list (fast path)."""
        from rethinkdb import r

        with ApiAdmin._rdb_context():
            result = list(
                r.table("domains")
                .get_all(r.args(domain_ids))
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "status",
                    "user",
                    "category",
                    "group",
                    "accessed",
                    "create_dict",
                    "tag",
                    "persistent",
                )
                .merge(
                    lambda d: {
                        "user_name": r.table("users")
                        .get(d["user"])
                        .default({"name": "[deleted]"})["name"],
                        "category_name": r.table("categories")
                        .get(d["category"])
                        .default({"name": "[deleted]"})["name"],
                        "group_name": r.table("groups")
                        .get(d["group"])
                        .default({"name": "[deleted]"})["name"],
                    }
                )
                .run(ApiAdmin._rdb_connection)
            )
        return result

    @staticmethod
    def list_templates(payload):
        """List templates. Managers see only their category."""
        category = (
            payload["category_id"] if payload.get("role_id") == "manager" else None
        )
        return ApiAdmin.ListTemplates(category)

    # ── Domain Details ───────────────────────────────────────────────────

    @staticmethod
    def get_domain_details(payload, domain_id):
        """Get detailed data for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        result = ApiAdmin.DesktopDetailsData(domain_id)
        if result is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return result

    @staticmethod
    def get_domain_viewer_data(payload, domain_id):
        """Get viewer data for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        result = ApiAdmin.DesktopViewerData(domain_id)
        if result is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return result

    @staticmethod
    def get_deployment_viewer_data(payload, deployment_id):
        """Get viewer data for a deployment."""
        AdminDomainsService.owns_domain_id(payload, deployment_id)
        result = ApiAdmin.DeploymentViewerData(deployment_id)
        if result is None:
            raise Error("not_found", f"Deployment {deployment_id} not found")
        return result

    # ── Domain Status ────────────────────────────────────────────────────

    @staticmethod
    def find_storages_by_domain_status(payload, status):
        """Scan every desktop domain with ``status`` and enqueue a
        ``find`` task for each distinct storage id.

        Ports v3 ``api_v3_admin_domains_find_storages`` from
        ``api/views/AdminDomainsView.py:375``. Managers are scoped to
        their own category via the ``kind_status_category`` secondary
        index.
        """
        if payload.get("role_id") == "manager":
            index_key = "kind_status_category"
            index_value = ["desktop", status, payload.get("category_id")]
        else:
            index_key = "kind_status"
            index_value = ["desktop", status]

        with ApiAdmin._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(index_value, index=index_key)
                .pluck({"create_dict": {"hardware": {"disks": True}}})
                .run(ApiAdmin._rdb_connection)
            )

        storage_ids = set()
        for domain in domains:
            disks = domain.get("create_dict", {}).get("hardware", {}).get("disks", [])
            for disk in disks:
                if disk.get("storage_id"):
                    storage_ids.add(disk["storage_id"])

        tasks_created = 0
        for storage_id in storage_ids:
            try:
                if not Storage.exists(storage_id):
                    continue
                Storage(storage_id).find(payload.get("user_id"))
                tasks_created += 1
            except Exception:
                notify_admin(
                    payload["user_id"],
                    "Error finding storage",
                    f"There was an error creating a find task for {storage_id}",
                    type="error",
                )
        return {"tasks_created": tasks_created}

    @staticmethod
    def get_domains_by_status(payload, status):
        """Get domains by status."""
        if status == "delete_pending":
            if payload.get("role_id", "") == "admin":
                return StorageProcessed.get_domains_delete_pending()
            else:
                return StorageProcessed.get_domains_delete_pending(
                    payload["category_id"]
                )
        elif payload.get("role_id", "") == "admin":
            return ApiAdmin.domains_status_minimal(status)
        return []

    # ── Domain Storage ───────────────────────────────────────────────────

    @staticmethod
    def get_domain_storage(payload, domain_id):
        """Get storage information for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        return ApiAdmin.get_domain_storage(domain_id)

    # ── Domain XML ───────────────────────────────────────────────────────

    @staticmethod
    def get_domain_xml(domain_id):
        """Get XML for a domain."""
        with ApiAdmin._rdb_context():
            domain = (
                r.table("domains")
                .get(domain_id)
                .default(None)
                .run(ApiAdmin._rdb_connection)
            )
        if domain is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return domain.get("xml")

    @staticmethod
    def update_domain_xml(domain_id, data):
        """Update XML for a domain."""
        with ApiAdmin._rdb_context():
            existing = (
                r.table("domains")
                .get(domain_id)
                .default(None)
                .run(ApiAdmin._rdb_connection)
            )
        if existing is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        data["status"] = "Updating"
        data["id"] = domain_id
        with ApiAdmin._rdb_context():
            r.table("domains").get(domain_id).update(data).run(ApiAdmin._rdb_connection)
            result = (
                r.table("domains")
                .get(domain_id)
                .pluck("xml")
                .run(ApiAdmin._rdb_connection)
            )
        clear_domains_field_cache()
        return result.get("xml")

    @staticmethod
    def get_domain_xml_and_protected(domain_id):
        """Return the domain xml plus its xml_protected_sections list."""
        with ApiAdmin._rdb_context():
            domain = (
                r.table("domains")
                .get(domain_id)
                .pluck("xml", "create_dict")
                .default(None)
                .run(ApiAdmin._rdb_connection)
            )
        if domain is None:
            raise Error("not_found", "Domain not found")
        return {
            "xml": domain.get("xml"),
            "protected": domain.get("create_dict", {}).get(
                "xml_protected_sections", []
            ),
        }

    @staticmethod
    def save_domain_xml_sections(domain_id, xml, protected):
        """Persist a rebuilt xml and its protected-section list."""
        with ApiAdmin._rdb_context():
            r.table("domains").get(domain_id).update(
                {
                    "xml": xml,
                    "create_dict": {"xml_protected_sections": protected},
                }
            ).run(ApiAdmin._rdb_connection)
        clear_domains_field_cache()

    @staticmethod
    def apply_xml_section_edits(domain_id, sections, protected):
        """Merge edited xml sections into the domain xml and persist.

        Composed helper so the route doesn't have to chain
        get_domain_xml_and_protected + merge_xml_sections + save itself.
        Returns the rebuilt full xml.
        """
        from api.services.xml_sections import merge_xml_sections

        domain = AdminDomainsService.get_domain_xml_and_protected(domain_id)
        new_xml = merge_xml_sections(domain["xml"], sections)
        AdminDomainsService.save_domain_xml_sections(domain_id, new_xml, protected)
        return new_xml

    # ── Template Tree ────────────────────────────────────────────────────

    @staticmethod
    def get_template_tree_list(payload, template_id):
        """Get template tree list."""
        return ApiAdmin.get_template_tree_list(template_id, payload["user_id"])

    @staticmethod
    def get_domain_template_tree(payload, desktop_id):
        """Get template tree for a specific domain."""
        AdminDomainsService.owns_domain_id(payload, desktop_id)
        return DomainsProcessed.domain_template_tree(desktop_id)

    # ── Multiple Actions ─────────────────────────────────────────────────

    @staticmethod
    def multiple_actions(payload, action, ids):
        """Perform actions on multiple domains."""
        for d_id in ids:
            AdminDomainsService.owns_domain_id(payload, d_id)
        ApiAdmin.multiple_actions(action, ids, payload["user_id"])
        clear_domains_field_cache()

    # ── Template Delete ──────────────────────────────────────────────────

    @staticmethod
    def delete_template(payload, template_id):
        """Delete a template."""
        DesktopEvents.templates_delete(template_id, payload["user_id"])
        clear_templates_cache()
        clear_domains_field_cache()

    # ── Domain Fields ────────────────────────────────────────────────────

    @staticmethod
    @cached(
        cache=domains_field_cache,
        key=lambda payload, field, kind: hashkey(
            payload.get("role_id"),
            payload.get("category_id"),
            field,
            kind,
        ),
    )
    def get_domains_field(payload, field, kind):
        """Get a specific field for domains of a kind."""
        return ApiAdmin.get_domains_field(field, kind, payload)

    # ── Domain Hardware ──────────────────────────────────────────────────

    @staticmethod
    def get_domain_hardware(payload, domain_id):
        """Get hardware details for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        return DomainsProcessed.get_domain_details_hardware(domain_id)

    # ── Bulk Status Changes ──────────────────────────────────────────────

    @staticmethod
    def change_desktops_status(current_status, target_status):
        """Change status for all desktops matching current status."""
        if target_status not in [
            "Shutting-down",
            "Stopping",
            "StartingPaused",
            "Failed",
        ]:
            raise Error("bad_request", "Invalid target status")
        DesktopsProcessed.admin_change_status(current_status, target_status)
        clear_domains_field_cache()

    @staticmethod
    def change_desktops_status_category(category, current_status, target_status):
        """Change status for desktops in a category matching current status."""
        if current_status not in ["Stopped", "Failed", "Started"]:
            raise Error("bad_request", "Invalid current status")
        if target_status not in ["Shutting-down", "Stopping", "StartingPaused"]:
            raise Error("bad_request", "Invalid target status")
        DesktopsProcessed.admin_change_status_category(
            category, current_status, target_status
        )
        clear_domains_field_cache()

    # ── Domain Storage Path ──────────────────────────────────────────────

    @staticmethod
    def update_domain_storage_path(domain_id, old_path, new_path):
        """Update the storage path of a domain."""
        result = DomainsProcessed.update_domain_path(domain_id, old_path, new_path)
        clear_domains_field_cache()
        return result

    # ── Domain Search Info ───────────────────────────────────────────────

    @staticmethod
    def get_domain_search_info(payload, domain_id):
        """Get domain info for search results."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        with ApiAdmin._rdb_context():
            # ``.default(None)`` BEFORE pluck — otherwise pluck on null
            # crashes with ReqlNonExistenceError before the if-check
            # below ever runs.
            domain = (
                r.table("domains")
                .get(domain_id)
                .default(None)
                .run(ApiAdmin._rdb_connection)
            )
        if not domain:
            raise Error("not_found", f"Domain {domain_id} not found")
        return {
            "id": domain.get("id"),
            "name": domain.get("name"),
            "status": domain.get("status"),
            "user": domain.get("user"),
            "kind": domain.get("kind"),
            "create_dict": {
                "hardware": {
                    "disks": (
                        (domain.get("create_dict") or {})
                        .get("hardware", {})
                        .get("disks", [])
                    )
                }
            },
            "owner_data": Caches.get_cached_user_with_names(domain.get("user")),
        }

    # ── Logs Desktops ────────────────────────────────────────────────────

    @staticmethod
    def set_logs_desktops_max_time(max_time):
        """Set max time for desktop logs old entries."""
        max_time = 24 if int(max_time) < 24 else int(max_time)
        return ApiAdmin.set_logs_desktops_old_entries_max_time(max_time)

    @staticmethod
    def set_logs_desktops_action(action):
        """Set action for desktop logs old entries.

        Route layer constrains ``action`` to ``Literal["delete", "none"]``.
        """
        return ApiAdmin.set_logs_desktops_old_entries_action(action)

    @staticmethod
    def get_logs_desktops_config():
        """Get desktop logs old entries configuration."""
        return ApiAdmin.get_logs_desktops_old_entries_config()

    @staticmethod
    def _delete_logs_async(table, event_name, max_time_arg=None):
        """Delete old logs asynchronously (shared logic)."""
        import gevent

        args = [table]
        if max_time_arg is not None:
            args.append(max_time_arg)
        old_logs = ApiAdmin.get_older_than_old_entry_max_time(*args)

        def delete_old_logs_process():
            try:
                with ApiAdmin._rdb_context():
                    batch_size = 50000
                    for i in range(0, len(old_logs), batch_size):
                        batch_ids = old_logs[i : i + batch_size]
                        r.table(table).get_all(r.args(batch_ids)).delete().run(
                            ApiAdmin._rdb_connection
                        )
                notify_admins(
                    event_name,
                    {"action": "delete_all", "status": "completed"},
                )
            except Error as e:
                log.error(traceback.format_exc())
                error_message = str(e)
                if isinstance(e.args, tuple) and len(e.args) > 1:
                    error_message = e.args[1]
                notify_admins(
                    event_name,
                    {
                        "action": "delete_all",
                        "msg": error_message,
                        "status": "failed",
                    },
                )
            except Exception:
                log.error(traceback.format_exc())
                notify_admins(
                    event_name,
                    {
                        "action": "delete_all",
                        "msg": "Something went wrong",
                        "status": "failed",
                    },
                )

        gevent.spawn(delete_old_logs_process)
        return len(old_logs)

    @staticmethod
    def delete_old_desktop_logs():
        """Delete old desktop logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action"
        )

    @staticmethod
    def delete_all_desktop_logs():
        """Delete all desktop logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action", 0
        )

    # ── Logs Users ───────────────────────────────────────────────────────

    @staticmethod
    def set_logs_users_max_time(max_time):
        """Set max time for user logs old entries."""
        max_time = 24 if int(max_time) < 24 else int(max_time)
        return ApiAdmin.set_logs_users_old_entries_max_time(max_time)

    @staticmethod
    def set_logs_users_action(action):
        """Set action for user logs old entries.

        Route layer constrains ``action`` to ``Literal["delete", "none"]``.
        """
        return ApiAdmin.set_logs_users_old_entries_action(action)

    @staticmethod
    def get_logs_users_config():
        """Get user logs old entries configuration."""
        return ApiAdmin.get_logs_users_old_entries_config()

    @staticmethod
    def delete_old_user_logs():
        """Delete old user logs asynchronously."""
        return AdminDomainsService._delete_logs_async("logs_users", "logs_users_action")

    @staticmethod
    def delete_all_user_logs():
        """Delete all user logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_users", "logs_users_action", 0
        )

    # ── Logs Queries ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_multi_form(form_data):
        """Parse DataTables multi-form data into nested dict."""
        data = {}
        for url_k in form_data:
            v = form_data[url_k]
            ks = []
            remaining = url_k
            while remaining:
                if "[" in remaining:
                    k, rest = remaining.split("[", 1)
                    ks.append(k)
                    if rest[0] == "]":
                        ks.append("")
                    remaining = rest.replace("]", "", 1)
                else:
                    ks.append(remaining)
                    break
            sub_data = data
            for i, k in enumerate(ks):
                if k.isdigit():
                    k = int(k)
                if i + 1 < len(ks):
                    if not isinstance(sub_data, dict):
                        break
                    if k in sub_data:
                        sub_data = sub_data[k]
                    else:
                        sub_data[k] = {}
                        sub_data = sub_data[k]
                else:
                    if isinstance(sub_data, dict):
                        sub_data[k] = v
        return data

    @staticmethod
    def _build_logs_query(table, form_data):
        """Build a RethinkDB query for logs tables with DataTables parameters."""
        ARRAY_LIMIT = 500000

        # Get table indexes
        with ApiAdmin._rdb_context():
            table_indexes = r.table(table).index_list().run(ApiAdmin._rdb_connection)

        query = r.table(table)
        skip_indexs = False

        # Add ordering
        if form_data.get("order") and len(form_data["order"]):
            order_field = form_data["columns"][int(form_data["order"][0]["column"])][
                "data"
            ]
            if order_field in table_indexes:
                if form_data["order"][0]["dir"] == "desc":
                    query = query.order_by(index=r.desc(order_field))
                else:
                    query = query.order_by(index=r.asc(order_field))
                if form_data.get("range") and order_field != form_data["range"].get(
                    "field"
                ):
                    skip_indexs = True
            else:
                orders = form_data["order"]
                if isinstance(orders, dict):
                    orders = orders.values()
                for order in orders:
                    col_idx = int(order["column"])
                    cols = form_data["columns"]
                    if isinstance(cols, dict):
                        cols = list(cols.values())
                    col_data = cols[col_idx]["data"] if col_idx < len(cols) else None
                    if col_data:
                        if order["dir"] == "desc":
                            query = query.order_by(r.desc(col_data))
                        else:
                            query = query.order_by(r.asc(col_data))

        # Add range filters
        if form_data.get("range"):
            s = form_data["range"].get("start")
            e = form_data["range"].get("end")
            range_field = form_data["range"].get("field")
            if s and e and range_field:
                start_str = (s if "T" in s else s + "T00:00:00") + "Z"
                end_str = (e if "T" in e else e + "T23:59:59") + "Z"
                if skip_indexs:
                    query = query.filter(
                        lambda doc: doc[range_field].during(
                            r.iso8601(start_str), r.iso8601(end_str)
                        )
                    )
                else:
                    query = query.between(
                        r.iso8601(start_str),
                        r.iso8601(end_str),
                        index=range_field,
                    )

        # Add search filters
        if form_data.get("columns"):
            columns_iter = form_data["columns"]
            if isinstance(columns_iter, dict):
                columns_iter = columns_iter.values()
            for column in columns_iter:
                if (
                    column.get("data", "") != ""
                    and column.get("search", {}).get("value", "") != ""
                ):
                    col_data = column["data"]
                    search_val = column["search"]["value"]
                    query = query.filter(
                        lambda doc, cd=col_data, sv=search_val: doc[cd].match(sv)
                    )

        # Add single-field filter (e.g. filter by desktop_id)
        if form_data.get("filter_field") and form_data.get("filter_value"):
            ff = form_data["filter_field"]
            fv = form_data["filter_value"]
            query = query.filter(lambda doc: doc[ff] == fv)

        # Add pluck
        if form_data.get("pluck"):
            query = query.pluck(form_data["pluck"])

        return query, table_indexes

    @staticmethod
    def _query_logs(table, form_data, view="raw"):
        """Execute a logs query with DataTables parameters."""
        if isinstance(form_data, dict):
            parsed = form_data
        else:
            parsed = AdminDomainsService._parse_multi_form(form_data)

        if view == "raw":
            query, table_indexes = AdminDomainsService._build_logs_query(table, parsed)

            with ApiAdmin._rdb_context():
                total = r.table(table).count().run(ApiAdmin._rdb_connection)
                filtered = query.count().run(ApiAdmin._rdb_connection)

                # Add pagination
                paged_query = query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged_query.run(ApiAdmin._rdb_connection))

            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": total,
                "recordsFiltered": filtered,
                "data": data,
                "indexs": table_indexes,
            }

        elif view == "desktop_grouping" and table == "logs_desktops":
            query, _ = AdminDomainsService._build_logs_query(table, parsed)
            group_query = r.table(table).group(index="desktop_id")
            group_query = (
                group_query.map(
                    lambda log_entry: {
                        "count": 1,
                        "desktop_name": log_entry["desktop_name"],
                        "desktop_id": log_entry["desktop_id"],
                        "owner_user_name": log_entry["owner_user_name"],
                        "owner_user_id": log_entry["owner_user_id"],
                        "owner_group_name": log_entry["owner_group_name"],
                        "owner_group_id": log_entry["owner_group_id"],
                        "owner_category_name": log_entry["owner_category_name"],
                        "owner_category_id": log_entry["owner_category_id"],
                        "starting_time": log_entry["starting_time"],
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "desktop_name": left["desktop_name"],
                        "desktop_id": left["desktop_id"],
                        "owner_user_name": left["owner_user_name"],
                        "owner_user_id": left["owner_user_id"],
                        "owner_group_name": left["owner_group_name"],
                        "owner_group_id": left["owner_group_id"],
                        "owner_category_name": left["owner_category_name"],
                        "owner_category_id": left["owner_category_id"],
                        "starting_time": right["starting_time"],
                    }
                )
                .ungroup()["reduction"]
            )
            with ApiAdmin._rdb_context():
                total = r.table(table).count().run(ApiAdmin._rdb_connection)
                filtered = query.count().run(ApiAdmin._rdb_connection)
                paged = group_query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged.run(ApiAdmin._rdb_connection))
            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": total,
                "recordsFiltered": filtered,
                "data": data,
                "indexs": [],
            }

        elif view == "user_grouping" and table == "logs_users":
            query, _ = AdminDomainsService._build_logs_query(table, parsed)
            group_query = r.table(table).group(index="owner_user_id")
            group_query = (
                group_query.map(
                    lambda log_entry: {
                        "count": 1,
                        "owner_user_name": log_entry["owner_user_name"],
                        "owner_user_id": log_entry["owner_user_id"],
                        "owner_group_name": log_entry["owner_group_name"],
                        "owner_group_id": log_entry["owner_group_id"],
                        "owner_category_name": log_entry["owner_category_name"],
                        "owner_category_id": log_entry["owner_category_id"],
                        "started_time": log_entry["started_time"],
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "owner_user_name": left["owner_user_name"],
                        "owner_user_id": left["owner_user_id"],
                        "owner_group_name": left["owner_group_name"],
                        "owner_group_id": left["owner_group_id"],
                        "owner_category_name": left["owner_category_name"],
                        "owner_category_id": left["owner_category_id"],
                        "started_time": right["started_time"],
                    }
                )
                .ungroup()["reduction"]
            )
            with ApiAdmin._rdb_context():
                total = r.table(table).count().run(ApiAdmin._rdb_connection)
                filtered = query.count().run(ApiAdmin._rdb_connection)
                paged = group_query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged.run(ApiAdmin._rdb_connection))
            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": total,
                "recordsFiltered": filtered,
                "data": data,
                "indexs": [],
            }

        elif view == "category_grouping":
            # Get category names for mapping
            with ApiAdmin._rdb_context():
                categories = {
                    item["id"]: item["name"]
                    for item in r.table("categories")
                    .pluck("id", "name")
                    .run(ApiAdmin._rdb_connection)
                }

            pluck_field = "desktop_id" if table == "logs_desktops" else "owner_user_id"
            cat_query = r.table(table).group(index="owner_category_id")

            # Apply range filters if present
            if parsed.get("range"):
                s = parsed["range"]["start"]
                e = parsed["range"]["end"]
                start_str = (s if "T" in s else s + "T00:00:00") + "Z"
                end_str = (e if "T" in e else e + "T23:59:59") + "Z"
                cat_query = cat_query.filter(
                    lambda doc: doc[parsed["range"]["field"]].during(
                        r.iso8601(start_str), r.iso8601(end_str)
                    )
                )

            cat_query = cat_query.pluck(pluck_field).distinct().count()

            with ApiAdmin._rdb_context():
                cat_data = cat_query.run(ApiAdmin._rdb_connection, array_limit=500000)

            # Get totals via group_by
            group_index = "owner_category_id"
            totals_query = r.table(table).group(index=group_index)
            if table == "logs_desktops":
                totals_query = (
                    totals_query.map(lambda log_entry: {"count": 1})
                    .reduce(
                        lambda left, right: {"count": left["count"] + right["count"]}
                    )
                    .ungroup()["reduction"]
                )
            else:
                totals_query = (
                    totals_query.map(lambda log_entry: {"count": 1})
                    .reduce(
                        lambda left, right: {"count": left["count"] + right["count"]}
                    )
                    .ungroup()["reduction"]
                )

            with ApiAdmin._rdb_context():
                totals = list(totals_query.run(ApiAdmin._rdb_connection))

            result_data = [
                {
                    "total": next(
                        (
                            t.get("count", 0)
                            for t in totals
                            if t.get("owner_category_id") == key
                        ),
                        0,
                    ),
                    "count": value,
                    "owner_category_name": categories.get(key, "[DELETED]" + key),
                    "owner_category_id": key,
                }
                for key, value in cat_data.items()
            ]

            # Sort
            if parsed.get("order") and len(parsed["order"]):
                col = parsed["order"][0].get("column", "0")
                if col == "1":
                    order_key = "total"
                elif col == "2":
                    order_key = "count"
                elif col == "3":
                    order_key = "owner_category_name"
                else:
                    order_key = "count"
                reverse = parsed["order"][0].get("dir", "asc") == "desc"
                result_data = sorted(
                    result_data, key=lambda x: x[order_key], reverse=reverse
                )

            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": len(result_data),
                "recordsFiltered": len(result_data),
                "data": result_data,
                "indexs": [],
            }

        return {}

    @staticmethod
    def query_logs_desktops(form_data, view="raw"):
        """Query desktop logs with DataTables parameters."""
        return AdminDomainsService._query_logs("logs_desktops", form_data, view)

    @staticmethod
    def query_logs_users(form_data, view="raw"):
        """Query user logs with DataTables parameters."""
        return AdminDomainsService._query_logs("logs_users", form_data, view)

    @staticmethod
    def list_desktop_logs(
        payload,
        start_date=None,
        end_date=None,
        limit=100,
        offset=0,
        desktop_id=None,
        user_id=None,
    ):
        """Simple list of desktop logs with filters (no DataTables)."""
        from rethinkdb import r

        query = r.table("logs_desktops")
        if payload.get("role_id") == "manager":
            query = query.filter({"owner_category_id": payload["category_id"]})
        if desktop_id:
            query = query.filter({"desktop_id": desktop_id})
        if user_id:
            query = query.filter({"owner_user_id": user_id})
        if start_date:
            s = (start_date if "T" in start_date else start_date + "T00:00:00") + "Z"
            query = query.filter(lambda d: d["starting_time"] >= r.iso8601(s))
        if end_date:
            e = (end_date if "T" in end_date else end_date + "T23:59:59") + "Z"
            query = query.filter(lambda d: d["starting_time"] <= r.iso8601(e))
        query = query.order_by(r.desc("starting_time")).skip(offset).limit(limit)
        with ApiAdmin._rdb_context():
            return list(query.run(ApiAdmin._rdb_connection))

    @staticmethod
    def list_user_logs(
        payload,
        start_date=None,
        end_date=None,
        limit=100,
        offset=0,
        user_id=None,
        group_id=None,
    ):
        """Simple list of user logs with filters (no DataTables)."""
        from rethinkdb import r

        query = r.table("logs_users")
        if payload.get("role_id") == "manager":
            query = query.filter({"category_id": payload["category_id"]})
        if user_id:
            query = query.filter({"user_id": user_id})
        if group_id:
            query = query.filter({"group_id": group_id})
        if start_date:
            s = (start_date if "T" in start_date else start_date + "T00:00:00") + "Z"
            query = query.filter(lambda d: d["starting_time"] >= r.iso8601(s))
        if end_date:
            e = (end_date if "T" in end_date else end_date + "T23:59:59") + "Z"
            query = query.filter(lambda d: d["starting_time"] <= r.iso8601(e))
        query = query.order_by(r.desc("starting_time")).skip(offset).limit(limit)
        with ApiAdmin._rdb_context():
            return list(query.run(ApiAdmin._rdb_connection))
