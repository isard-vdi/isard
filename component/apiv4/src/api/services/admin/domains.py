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
import os
import traceback
from typing import Optional

from api.services.error import Error
from api.services.templates import clear_templates_cache
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from fastapi import BackgroundTasks
from isardvdi_common.helpers.api_notify import notify_admin, notify_admins
from isardvdi_common.helpers.backup_writer import BackupWriter
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.lib.domains.domains import DomainsProcessed
from isardvdi_common.lib.logs.logs import LogsProcessed
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.storage import Storage

domains_field_cache = TTLCache(maxsize=50, ttl=5)


def clear_domains_field_cache() -> None:
    domains_field_cache.clear()


class AdminDomainsService:
    """
    Service for admin domain management operations.
    """

    # ── Ownership Checks ─────────────────────────────────────────────────

    @staticmethod
    def owns_domain_id(payload: dict, domain_id: str) -> None:
        """Check if the admin/manager owns the domain."""
        Helpers.owns_domain_id(payload, domain_id)

    # ── List Domains ─────────────────────────────────────────────────────

    @staticmethod
    def list_desktops(payload: dict, categories: Optional[str] = None) -> list[dict]:
        """List desktops, optionally filtered by categories."""
        if payload["role_id"] == "manager":
            categories = [payload["category_id"]]
        elif categories:
            categories = (
                json.loads(categories) if isinstance(categories, str) else categories
            )
        return ApiAdmin.ListDesktops(categories)

    @staticmethod
    def get_domains_by_ids(payload: dict, domain_ids: list[str]) -> list[dict]:
        """Get specific domains by ID list (fast path)."""
        return DomainsProcessed.get_by_ids(domain_ids)

    @staticmethod
    def list_templates(payload: dict) -> list[dict]:
        """List templates. Managers see only their category."""
        category = (
            payload["category_id"] if payload.get("role_id") == "manager" else None
        )
        return ApiAdmin.ListTemplates(category)

    # ── Domain Details ───────────────────────────────────────────────────

    @staticmethod
    def get_domain_details(payload: dict, domain_id: str) -> dict:
        """Get detailed data for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        result = ApiAdmin.DesktopDetailsData(domain_id)
        if result is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return result

    @staticmethod
    def get_domain_viewer_data(payload: dict, domain_id: str) -> dict:
        """Get viewer data for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        result = ApiAdmin.DesktopViewerData(domain_id)
        if result is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return result

    @staticmethod
    def get_deployment_viewer_data(payload: dict, deployment_id: str) -> dict:
        """Get viewer data for a deployment."""
        AdminDomainsService.owns_domain_id(payload, deployment_id)
        result = ApiAdmin.DeploymentViewerData(deployment_id)
        if result is None:
            raise Error("not_found", f"Deployment {deployment_id} not found")
        return result

    # ── Domain Status ────────────────────────────────────────────────────

    @staticmethod
    def find_storages_by_domain_status(payload: dict, status: str) -> dict:
        """Scan every desktop domain with ``status`` and enqueue a
        ``find`` task for each distinct storage id.

        Ports v3 ``api_v3_admin_domains_find_storages`` from
        ``api/views/AdminDomainsView.py:375``. Managers are scoped to
        their own category via the ``kind_status_category`` secondary
        index.
        """
        category_id = (
            payload.get("category_id") if payload.get("role_id") == "manager" else None
        )
        domains = DomainsProcessed.find_disks_by_kind_status(
            "desktop", status, category_id=category_id
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
    def get_domains_by_status(payload: dict, status: str) -> list[dict]:
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
    def get_domain_storage(payload: dict, domain_id: str) -> list[dict]:
        """Get storage information for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        return ApiAdmin.get_domain_storage(domain_id)

    # ── Domain XML ───────────────────────────────────────────────────────

    @staticmethod
    def get_domain_xml(domain_id: str) -> Optional[str]:
        """Get XML for a domain."""
        return DomainsProcessed.get_xml(domain_id)

    @staticmethod
    def update_domain_xml(domain_id: str, data: dict) -> Optional[str]:
        """Update XML for a domain."""
        result = DomainsProcessed.update_xml(domain_id, data)
        clear_domains_field_cache()
        return result

    @staticmethod
    def get_domain_xml_and_protected(domain_id: str) -> dict:
        """Return the domain xml plus its xml_protected_sections list."""
        return DomainsProcessed.get_xml_and_protected(domain_id)

    @staticmethod
    def save_domain_xml_sections(
        domain_id: str, xml: str, protected: list[str]
    ) -> None:
        """Persist a rebuilt xml and its protected-section list.

        Delegates to ``XmlSectionsProcessed.update_domain_xml_and_protected``
        which wraps ``protected`` in ``r.literal(...)`` so removed
        sections actually disappear from the persisted array (the
        previous inline version omitted ``r.literal`` and so could not
        shrink the protected list).
        """
        from isardvdi_common.lib.domains.xml_sections import XmlSectionsProcessed

        XmlSectionsProcessed.update_domain_xml_and_protected(domain_id, xml, protected)
        clear_domains_field_cache()

    @staticmethod
    def apply_xml_section_edits(
        domain_id: str, sections: dict, protected: list[str]
    ) -> str:
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
    def get_template_tree_list(payload: dict, template_id: str) -> list[dict]:
        """Get template tree list."""
        return ApiAdmin.get_template_tree_list(template_id, payload["user_id"])

    @staticmethod
    def get_domain_template_tree(payload: dict, desktop_id: str) -> list[dict]:
        """Get template tree for a specific domain."""
        AdminDomainsService.owns_domain_id(payload, desktop_id)
        return DomainsProcessed.domain_template_tree(desktop_id)

    # ── Multiple Actions ─────────────────────────────────────────────────

    @staticmethod
    def multiple_actions(
        payload: dict,
        action: str,
        ids: list[str],
        background_tasks: BackgroundTasks,
    ) -> None:
        """Perform actions on multiple domains.

        The bulk action runs after the response is sent (FastAPI default
        thread pool). Originally v3 used ``gevent.spawn`` here; that
        silently never ran inside the asyncio worker and was the
        Tier-B remediation site in
        ``APIV4_THREADING_INCIDENT_ANALYSIS.md``.
        """
        for d_id in ids:
            AdminDomainsService.owns_domain_id(payload, d_id)
        background_tasks.add_task(
            ApiAdmin.multiple_actions, action, ids, payload["user_id"]
        )
        clear_domains_field_cache()

    # ── Template Delete ──────────────────────────────────────────────────

    @staticmethod
    def delete_template(payload: dict, template_id: str) -> None:
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
    def get_domains_field(payload: dict, field: str, kind: str) -> dict:
        """Get the distinct values for a domain field as ``{"field": [...]}``."""
        return ApiAdmin.get_domains_field(field, kind, payload)

    # ── Domain Hardware ──────────────────────────────────────────────────

    @staticmethod
    def get_domain_hardware(payload: dict, domain_id: str) -> dict:
        """Get hardware details for a domain."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        return DomainsProcessed.get_domain_details_hardware(domain_id)

    # ── Bulk Status Changes ──────────────────────────────────────────────

    @staticmethod
    def change_desktops_status(current_status: str, target_status: str) -> None:
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
    def change_desktops_status_category(
        category: str, current_status: str, target_status: str
    ) -> None:
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
    def update_domain_storage_path(
        domain_id: str, old_path: str, new_path: str
    ) -> dict:
        """Update the storage path of a domain."""
        result = DomainsProcessed.update_domain_path(domain_id, old_path, new_path)
        clear_domains_field_cache()
        return result

    # ── Domain Search Info ───────────────────────────────────────────────

    @staticmethod
    def get_domain_search_info(payload: dict, domain_id: str) -> dict:
        """Get domain info for search results."""
        AdminDomainsService.owns_domain_id(payload, domain_id)
        domain = DomainsProcessed.get_for_search(domain_id)
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
    def set_logs_desktops_max_time(max_time: int) -> None:
        """Set max time for desktop logs old entries."""
        max_time = 24 if int(max_time) < 24 else int(max_time)
        return ApiAdmin.set_logs_desktops_old_entries_max_time(max_time)

    @staticmethod
    def set_logs_desktops_action(action: str) -> None:
        """Set action for desktop logs old entries.

        Route layer constrains ``action`` to ``Literal["delete", "none"]``.
        """
        return ApiAdmin.set_logs_desktops_old_entries_action(action)

    @staticmethod
    def get_logs_desktops_config() -> dict:
        """Get desktop logs old entries configuration."""
        return ApiAdmin.get_logs_desktops_old_entries_config()

    @staticmethod
    def _delete_logs_async(
        table: str,
        event_name: str,
        background_tasks: BackgroundTasks,
        max_time_arg: Optional[int] = None,
    ) -> int:
        """Delete old logs asynchronously (shared logic).

        When ``LOGS_DELETE_BACKUP_DIR`` env var is set, every row that
        is about to be deleted is first streamed to a gzipped JSONL
        file at ``<dir>/<table>_delete_<UTC-ts>.jsonl.gz``. Restoring
        the dump into the same table is a one-line ``rethinkdb-cli``
        ``insert`` so the destructive cron is recoverable.
        """
        args = [table]
        if max_time_arg is not None:
            args.append(max_time_arg)
        old_logs = ApiAdmin.get_older_than_old_entry_max_time(*args)
        backup_dir = os.environ.get("LOGS_DELETE_BACKUP_DIR")

        def delete_old_logs_process() -> None:
            try:
                backup_path: Optional[str] = None
                if backup_dir and old_logs:
                    with BackupWriter(backup_dir, f"{table}_delete") as backup:
                        LogsProcessed.delete_batch(table, old_logs, backup=backup)
                        backup_path = backup.path
                else:
                    LogsProcessed.delete_batch(table, old_logs)
                payload = {"action": "delete_all", "status": "completed"}
                if backup_path is not None:
                    payload["backup_path"] = backup_path
                notify_admins(event_name, payload)
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

        # FastAPI runs this in its default thread-pool after the response,
        # replacing a gevent.spawn that silently never executed inside the
        # asyncio worker. See APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.
        background_tasks.add_task(delete_old_logs_process)
        return len(old_logs)

    @staticmethod
    def delete_old_desktop_logs(background_tasks: BackgroundTasks) -> int:
        """Delete old desktop logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action", background_tasks
        )

    @staticmethod
    def delete_all_desktop_logs(background_tasks: BackgroundTasks) -> int:
        """Delete all desktop logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_desktops", "logs_desktops_action", background_tasks, 0
        )

    # ── Logs Users ───────────────────────────────────────────────────────

    @staticmethod
    def set_logs_users_max_time(max_time: int) -> None:
        """Set max time for user logs old entries."""
        max_time = 24 if int(max_time) < 24 else int(max_time)
        return ApiAdmin.set_logs_users_old_entries_max_time(max_time)

    @staticmethod
    def set_logs_users_action(action: str) -> None:
        """Set action for user logs old entries.

        Route layer constrains ``action`` to ``Literal["delete", "none"]``.
        """
        return ApiAdmin.set_logs_users_old_entries_action(action)

    @staticmethod
    def get_logs_users_config() -> dict:
        """Get user logs old entries configuration."""
        return ApiAdmin.get_logs_users_old_entries_config()

    @staticmethod
    def delete_old_user_logs(background_tasks: BackgroundTasks) -> int:
        """Delete old user logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_users", "logs_users_action", background_tasks
        )

    @staticmethod
    def delete_all_user_logs(background_tasks: BackgroundTasks) -> int:
        """Delete all user logs asynchronously."""
        return AdminDomainsService._delete_logs_async(
            "logs_users", "logs_users_action", background_tasks, 0
        )

    # ── Logs Queries ─────────────────────────────────────────────────────

    @staticmethod
    def _query_logs(
        table: str,
        body: dict,
        view: str = "raw",
        payload: Optional[dict] = None,
    ) -> dict:
        """Execute a logs query with DataTables parameters.

        ``payload`` carries the JWT data; managers see only their own
        category (apiv3 ``@is_admin_or_manager`` parity), admins see
        everything.
        """
        scope_category_id = (
            payload["category_id"]
            if payload and payload.get("role_id") == "manager"
            else None
        )
        return LogsProcessed.query_paginated(
            table, body, view=view, scope_category_id=scope_category_id
        )

    @staticmethod
    def query_logs_desktops(
        body: dict, view: str = "raw", payload: Optional[dict] = None
    ) -> dict:
        """Query desktop logs with DataTables parameters."""
        return AdminDomainsService._query_logs(
            "logs_desktops", body, view, payload=payload
        )

    @staticmethod
    def query_logs_users(
        body: dict, view: str = "raw", payload: Optional[dict] = None
    ) -> dict:
        """Query user logs with DataTables parameters."""
        return AdminDomainsService._query_logs(
            "logs_users", body, view, payload=payload
        )

    @staticmethod
    def list_desktop_logs(
        payload: dict,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        desktop_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Simple list of desktop logs with filters (no DataTables)."""
        category_id = (
            payload["category_id"] if payload.get("role_id") == "manager" else None
        )
        return LogsProcessed.list_simple_desktop(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
            desktop_id=desktop_id,
            user_id=user_id,
        )

    @staticmethod
    def list_user_logs(
        payload: dict,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> list[dict]:
        """Simple list of user logs with filters (no DataTables)."""
        category_id = (
            payload["category_id"] if payload.get("role_id") == "manager" else None
        )
        return LogsProcessed.list_simple_user(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
            user_id=user_id,
            group_id=group_id,
        )
