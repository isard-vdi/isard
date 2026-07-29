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

import logging as log
import os
import time
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

import requests

if TYPE_CHECKING:
    from isardvdi_common.models.storage import Storage

from api.schemas.admin.downloads import REGISTRY_ENTRY_MODELS
from api.services.admin.tables import AdminTablesService
from api.services.cards import CardService
from cachetools import cached
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.helpers.xml_compression import decompress_xml
from isardvdi_common.lib.downloads.downloads import DownloadsProcessed
from isardvdi_common.models.config import Config
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.task import Task
from pydantic import ValidationError

# Mirror ``api.services.media`` so registry-domain downloads honour the
# same ``URL_DOWNLOAD_INSECURE_SSL`` toggle the legacy engine path used.
URL_DOWNLOAD_INSECURE_SSL = (
    os.environ.get("URL_DOWNLOAD_INSECURE_SSL", "true").lower() == "true"
)


def _registry_rejection(kind: str, entry: dict) -> Optional[str]:
    """Why this registry entry must not become a row, or None if it may.

    What the updates server publishes is inserted almost verbatim, so a
    malformed entry does not fail here: it creates a row this
    installation cannot show. A domain whose kind is outside the
    taxonomy falls out of every kind-scoped query, leaving a desktop its
    owner never sees and cannot delete while it holds a disk.
    """
    model = REGISTRY_ENTRY_MODELS.get(kind)
    if model is None or not isinstance(entry, dict):
        return None
    try:
        model.model_validate(entry)
    except ValidationError as exc:
        return "; ".join(
            "{}: {}".format(
                ".".join(str(part) for part in error.get("loc", ())) or "entry",
                error.get("msg", "is invalid"),
            )
            for error in exc.errors()
        )
    return None


def _servable_entries(kind: str, entries: list) -> list:
    """Drop what an installation could not use, saying why.

    Dropping rather than raising on purpose: this runs while listing the
    catalogue, which is cached and shared, so one bad entry upstream must
    not cost every other template on the page.
    """
    kept = []
    for entry in entries:
        rejection = _registry_rejection(kind, entry)
        if rejection:
            log.warning(
                "Not offering %s entry %r published by the updates server: %s",
                kind,
                (entry or {}).get("name") if isinstance(entry, dict) else entry,
                rejection,
            )
            continue
        kept.append(entry)
    return kept


# Named caches so writers can invalidate them after mutations
# (the registration flow updates the code in the DB and must wipe
# the cached cfg/web kinds).
_get_cfg_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=1, ttl=360)
_download_web_kind_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=10, ttl=360
)
_download_web_private_kind_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=10, ttl=360
)
_get_web_kinds_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=1, ttl=360)


def clear_admin_downloads_caches() -> None:
    """Clear all admin downloads caches (used after registration)."""
    _get_cfg_cache.clear()
    _download_web_kind_cache.clear()
    _download_web_private_kind_cache.clear()
    _get_web_kinds_cache.clear()


class AdminDownloadsService:

    @staticmethod
    @cached(cache=_get_cfg_cache)
    def _get_cfg() -> tuple[str, str | bool, str | bool]:
        """Get download configuration from database."""
        cfg = Config.get_resources_config()
        return (
            cfg["url"],
            cfg["code"],
            cfg.get("private_code", False),
        )

    @staticmethod
    def check_registered() -> bool:
        """Check if IsardVDI is registered with the updates server."""
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        url, code, _ = AdminDownloadsService._get_cfg()
        # Surface as a typed bad_request; the outer ``except`` would
        # otherwise swallow the ValueError into a generic gateway_timeout.
        try:
            validate_url_not_internal(url)
        except ValueError as e:
            raise Error(
                "bad_request",
                str(e),
                description_code="updates_url_internal",
            )
        try:
            req = requests.get(url, allow_redirects=False, timeout=10)
            if req.status_code == 200:
                if not code:
                    raise Error(
                        "precondition_required",
                        "IsardVDI hasn't been registered yet.",
                    )
                return True
        except Error:
            raise
        except Exception:
            pass
        raise Error(
            "gateway_timeout",
            "There is a network or update server error at the moment. Try again later.",
        )

    @staticmethod
    def register() -> bool:
        """Register with the updates server."""
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        url, code, _ = AdminDownloadsService._get_cfg()
        if code:
            return True
        # The updates-server URL is admin-writable DB config; reject
        # values pointing at internal infrastructure (SSRF).
        try:
            validate_url_not_internal(url)
        except ValueError as e:
            raise Error(
                "bad_request",
                str(e),
                description_code="updates_url_internal",
            )
        try:
            req = requests.post(url + "/register", allow_redirects=False, timeout=10)
            if req.status_code == 200:
                Config.set_resources_code(req.json())
                _get_cfg_cache.clear()
                return True
        except Exception:
            pass
        return False

    @staticmethod
    @cached(cache=_download_web_kind_cache)
    def _download_web_kind(kind: str) -> list | int | bool:
        """Download a specific kind from the updates server."""
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        url, code, _ = AdminDownloadsService._get_cfg()
        # Reject admin-set URLs pointing at internal infrastructure (SSRF).
        try:
            validate_url_not_internal(url)
        except ValueError as e:
            raise Error(
                "bad_request",
                str(e),
                description_code="updates_url_internal",
            )
        try:
            req = requests.post(
                url + "/get/" + kind + "/list",
                headers={"Authorization": str(code)},
                allow_redirects=False,
                timeout=10,
            )
            if req.status_code == 200:
                if kind in ["domains", "media"]:
                    downloads = []
                    for d in req.json():
                        d["id"] = d.get("url-isard")
                        downloads.append(d)
                    return _servable_entries(kind, downloads)
                else:
                    return req.json()
            elif req.status_code == 500:
                return 500
        except Exception:
            pass
        return False

    @staticmethod
    @cached(cache=_download_web_private_kind_cache)
    def _download_web_private_kind(kind: str = "private_domains") -> list | bool:
        """Download private kind from the updates server."""
        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        url, code, private_code = AdminDownloadsService._get_cfg()
        # Reject admin-set URLs pointing at internal infrastructure (SSRF).
        try:
            validate_url_not_internal(url)
        except ValueError as e:
            raise Error(
                "bad_request",
                str(e),
                description_code="updates_url_internal",
            )
        try:
            req = requests.post(
                url + "/private_get/" + kind + "/list",
                headers={"Authorization": str(code)},
                json={"private_code": private_code},
                allow_redirects=False,
                timeout=10,
            )
            if req.status_code == 200:
                return _servable_entries(kind, req.json())
        except Exception:
            pass
        return False

    @staticmethod
    @cached(cache=_get_web_kinds_cache)
    def _get_web_kinds() -> dict:
        """Get all web kinds from the updates server."""
        web = {}
        kinds = ["media", "domains", "virt_install", "videos", "viewers"]
        for k in kinds:
            web[k] = AdminDownloadsService._download_web_kind(kind=k)
            if web[k] == 500:
                Config.set_resources_code(False)
        _, _, private_code = AdminDownloadsService._get_cfg()
        if private_code:
            private_web = AdminDownloadsService._download_web_private_kind(
                kind="private_domains"
            )
            if private_web:
                web["domains"] = web["domains"] + private_web
        return web

    @staticmethod
    def get_downloads() -> dict:
        """Get downloads overview (requires registration check)."""
        AdminDownloadsService.check_registered()
        return {}

    @staticmethod
    def get_downloads_kind(kind: str, user_id: str) -> list:
        """Get available downloads for a specific kind."""
        AdminDownloadsService.check_registered()
        web = AdminDownloadsService._get_web_kinds()
        # Defence in depth — the route layer already constrains ``kind``
        # via ``Literal[...]``, but a stale generated client or direct
        # service-layer call could still pass an unknown value. A
        # ``KeyError`` here would surface as a generic 500 with no
        # actionable description.
        if kind not in web:
            from api.services.error import Error

            raise Error(
                "bad_request",
                f"Unknown download kind {kind!r}; expected one of {sorted(web)}",
                description_code="bad_kind",
            )
        if kind == "viewers":
            return web[kind]

        web_items = web[kind]
        result = []

        if kind in ["domains", "media"]:
            dbb = DownloadsProcessed.list_user_kind_downloads(kind, user_id)
            dbb_dict = {d["url-isard"]: d for d in dbb}
            if kind == "media":
                mbb = DownloadsProcessed.list_user_media_url_web_downloads(user_id)
                dbb_dict = {
                    **dbb_dict,
                    **{d["url-web"]: d for d in mbb if d["url-web"]},
                }
            for w in web_items:
                if w["url-isard"] in dbb_dict.keys() or w["url-web"] in dbb_dict.keys():
                    key = w["url-isard"] if w["url-isard"] in dbb_dict else w["url-web"]
                    result.append(
                        {
                            **w,
                            "id": dbb_dict[key]["id"],
                            "new": False,
                            "status": dbb_dict[key]["status"],
                            "progress": dbb_dict[key].get("progress"),
                        }
                    )
                else:
                    result.append(
                        {
                            **w,
                            "id": str(uuid4()),
                            "new": True,
                            "status": "Available",
                        }
                    )
        else:
            dbb = DownloadsProcessed.list_table_rows(kind)
            for w in web_items:
                if w["id"] in [d["id"] for d in dbb]:
                    result.append({**w, "new": False, "status": "Downloaded"})
                else:
                    result.append({**w, "new": True, "status": "Available"})

        return result

    @staticmethod
    def download_action(
        action: str,
        kind: str,
        user_id: str,
        id: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> dict:
        """Execute a download action (download, abort, delete)."""
        AdminDownloadsService.check_registered()

        if action == "download":
            if id:
                if data is None:
                    # Webapp / Vue clients always send the row dict in
                    # the body (see webapp/static/admin/js/updates.js).
                    # API-only callers (CI integration tests, scripts)
                    # can rely on the id alone — fetch the matching
                    # registry entry server-side so the download still
                    # fires.
                    #
                    # Subtlety: for "new" (not-yet-downloaded) items
                    # ``get_downloads_kind`` minted a fresh ``uuid4()``
                    # for ``id`` on every call, so the id passed by an
                    # API client may not appear in the newest GET.
                    # Match against the stable ``url-isard`` /
                    # ``url-web`` canonical keys as well, and against
                    # ``name`` as a last resort. Failing through
                    # silently was the old behavior the integration
                    # suite surfaced.
                    items = AdminDownloadsService.get_downloads_kind(kind, user_id)
                    matches = [
                        d
                        for d in items
                        if d.get("id") == id
                        or d.get("url-isard") == id
                        or d.get("url-web") == id
                        or d.get("name") == id
                    ]
                    if not matches:
                        raise Error(
                            "not_found",
                            f"No registry {kind} entry matching id "
                            f"{id!r}; pass the row body or use a stable "
                            f"identifier (url-isard / url-web / name).",
                        )
                    data = matches[0]
                if data:
                    rejection = _registry_rejection(kind, data)
                    if rejection:
                        raise Error(
                            "bad_request",
                            f"This {kind} entry is not a valid row and was "
                            f"refused: {rejection}. Fix it where it is "
                            f"published, in the updates registry.",
                            description_code="registry_entry_invalid",
                        )
                if data and kind == "domains":
                    missing_resources = AdminDownloadsService._get_missing_resources(
                        data, user_id
                    )
                    for k, v in missing_resources.items():
                        for resource in v:
                            try:
                                AdminTablesService.insert_table_item(k, resource)
                            except Exception:
                                AdminTablesService.update_table_item(k, resource)
                if data:
                    pending_storage = None
                    if kind == "domains":
                        data = AdminDownloadsService._format_domains([data], user_id)[0]
                        pending_storage = (
                            AdminDownloadsService._allocate_storage_for_pending_domain(
                                data, user_id
                            )
                        )
                    elif kind == "media":
                        data = AdminDownloadsService._format_medias([data], user_id)[0]
                    try:
                        AdminTablesService.insert_table_item(kind, data)
                    except Exception:
                        AdminTablesService.update_table_item(kind, data)
                    AdminDownloadsService._kick_off_download_chain(
                        kind,
                        data,
                        pending_storage=pending_storage,
                        insecure_ssl=URL_DOWNLOAD_INSECURE_SSL,
                    )
            else:
                items = AdminDownloadsService.get_downloads_kind(kind, user_id)
                items = [d for d in items if d.get("new") is True]
                # One bad entry must not block the good ones, but if that
                # leaves nothing, say so rather than report success.
                offered = len(items)
                items = _servable_entries(kind, items)
                if offered and not items:
                    raise Error(
                        "bad_request",
                        f"None of the {offered} {kind} entries the updates "
                        f"registry offers is a valid row; nothing was "
                        f"downloaded. Fix them where they are published.",
                        description_code="registry_entry_invalid",
                    )
                if kind == "domains":
                    items = AdminDownloadsService._format_domains(items, user_id)
                elif kind == "media":
                    items = AdminDownloadsService._format_medias(items, user_id)
                for item in items:
                    pending_storage = None
                    if kind == "domains":
                        pending_storage = (
                            AdminDownloadsService._allocate_storage_for_pending_domain(
                                item, user_id
                            )
                        )
                    try:
                        AdminTablesService.insert_table_item(kind, item)
                    except Exception:
                        AdminTablesService.update_table_item(kind, item)
                    AdminDownloadsService._kick_off_download_chain(
                        kind,
                        item,
                        pending_storage=pending_storage,
                        insecure_ssl=URL_DOWNLOAD_INSECURE_SSL,
                    )
        elif action in ("abort", "delete"):
            if kind == "media":
                return AdminDownloadsService._media_action(action, id, user_id)
            if kind == "domains":
                return AdminDownloadsService._domain_action(action, id, user_id)
            if action == "delete":
                AdminTablesService.delete_table_item(kind, id)

        return {}

    @staticmethod
    def _media_action(action: str, id: str, user_id: str) -> dict:
        """Abort or delete a downloaded media, doing the work."""
        # lazy: avoids services->routes->services cycle
        from api.services.media import MediaService

        if action == "abort":
            MediaService.abort_media_download(id)
            return {"id": id, "kind": "media", "action": action}
        task = MediaService.delete_media(id, {"user_id": user_id})
        return {"id": id, "kind": "media", "action": action, "task_id": task}

    @staticmethod
    def _domain_storage_task(domain) -> Optional[str]:
        """The task of the storage this download writes into, if any."""
        disks = (domain.create_dict or {}).get("hardware", {}).get("disks") or []
        for disk in disks:
            storage_id = disk.get("storage_id") if isinstance(disk, dict) else None
            if not storage_id:
                continue
            from isardvdi_common.models.storage import Storage

            if Storage.exists(storage_id):
                return Storage(storage_id).task
        return None

    @staticmethod
    def _domain_action(action: str, id: str, user_id: str) -> dict:
        """Abort or delete a downloaded desktop, doing the work.

        The status was the whole implementation before: it wrote
        ``Deleting`` and waited for a consumer that no longer exists,
        which the engine's broom then rewrote to ``Unknown``. Nothing
        ever reached the storage worker.
        """
        # lazy: avoids services->routes->services cycle
        from api.services.desktops import DesktopService

        if not RethinkDomain.exists(id):
            raise Error(
                "not_found",
                f"Desktop with ID {id} not found.",
                description_code="not_found",
            )
        domain = RethinkDomain(id)
        status = domain.status
        in_flight = ("DownloadStarting", "Downloading", "Download")
        task_id = AdminDownloadsService._domain_storage_task(domain)
        pending = bool(task_id and Task.exists(task_id) and Task(task_id).pending)

        if action == "abort":
            if status not in in_flight + ("DownloadAborting", "ResetDownloading"):
                raise Error(
                    "bad_request",
                    f"There is no download to abort for {id}; its status is "
                    f"{status}.",
                    description_code="download_not_running",
                )
            domain.status = "DownloadAborting"
            if pending:
                try:
                    Task(task_id).cancel()
                except Exception:
                    # Best effort: the row flag still stops the worker on
                    # its next check, and the chain settles the row.
                    pass
            else:
                # No chain will ever finalize this row, so settle it here
                # instead of leaving it aborting for good.
                domain.status = "Failed"
            return {"id": id, "kind": "domains", "action": action}

        if status in in_flight:
            raise Error(
                "precondition_required",
                f"{id} is downloading; abort the download before deleting it.",
                description_code="download_in_progress",
            )
        if pending:
            raise Error(
                "precondition_required",
                f"{id} has the pending task {task_id}; wait for it to settle.",
                description_code="download_task_pending",
            )
        if domain.kind != "desktop":
            # A row with a kind outside the taxonomy is not something the
            # desktop delete can reason about; it needs repairing first.
            raise Error(
                "precondition_required",
                f"{id} has the unsupported kind {domain.kind!r} and cannot be "
                "deleted until it is repaired.",
                description_code="download_row_unsupported_kind",
            )
        # Always permanent: the Downloads page is where an operator goes
        # to free the space, and the entry can be downloaded again.
        tasks = DesktopService.delete_desktop(id, user_id=user_id, permanent=True)
        return {"id": id, "kind": "domains", "action": action, "task_id": tasks}

    @staticmethod
    def _get_missing_resources(domain: dict, username: str) -> dict:
        """Check for missing resources required by a domain."""
        missing_resources = {"videos": []}
        dom_videos = domain["create_dict"]["hardware"]["videos"]
        sys_video_ids = DownloadsProcessed.list_video_ids()
        for v in dom_videos:
            if v not in sys_video_ids:
                resource = AdminDownloadsService._get_new_kind_id("videos", username, v)
                if resource:
                    missing_resources["videos"].append(resource)
        return missing_resources

    @staticmethod
    def _get_new_kind_id(kind: str, username: str, id: str) -> dict | bool:
        """Get a specific item from the updates server by ID."""
        web = AdminDownloadsService._get_web_kinds()
        web_items = [d.copy() for d in web[kind] if d["id"] == id]
        if not web_items:
            return False
        w = web_items[0].copy()
        if kind in ("domains", "media"):
            dbb = DownloadsProcessed.find_user_kind_by_url(kind, username, w["id"])
            if not dbb:
                dbb = DownloadsProcessed.find_user_kind_by_url_web(
                    kind, username, w["id"]
                )
            if not dbb:
                w["id"] = str(uuid4())
                return w
            elif dbb[0].get("status") == "DownloadFailed":
                return dbb[0]
        else:
            from isardvdi_common.lib.api_admin import ApiAdmin

            dbb = ApiAdmin.get_table_item(kind, w["id"])
            if dbb is None:
                return w
        return False

    @staticmethod
    def _parse_xml_protection_hints(xml_str: str) -> dict:
        """Derive engine-consumed hardware protection hints from registry XML.

        The engine's start pipeline mutates the registry XML in place
        (``engine/models/domain_xml.py:recreate_xml_to_start``): it replaces
        the ``<cpu>`` section with host-model and rebuilds ``<interface>``
        and ``<video>`` elements from DB rows. That clobbers guests whose
        registry XML encodes a specific CPU model or legacy NIC/video
        driver (e.g. TetrOS ships ``kvm32`` CPU and ``rtl8139`` NIC).

        This helper inspects the XML and returns two pre-existing escape
        hatches the engine already honours:
          * ``not_change_cpu_section`` — gates ``set_cpu_host_model``
            (domain_xml.py:1858-1859).
          * ``protected_sections`` — list consumed via
            ``create_dict.xml_protected_sections`` (domain_xml.py:1700-1704).

        Parse failures or missing XML yield empty hints so downloads never
        fail on malformed registry entries.
        """
        result = {"not_change_cpu_section": False, "protected_sections": []}
        if not xml_str:
            return result
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return result

        cpu = root.find("cpu")
        if cpu is not None:
            mode = cpu.get("mode", "")
            model_el = cpu.find("model")
            model_text = (model_el.text or "").strip() if model_el is not None else ""
            if (
                mode == "custom"
                and model_text
                and model_text not in ("host-model", "host-passthrough")
            ):
                result["not_change_cpu_section"] = True
                result["protected_sections"].append("cpu")

        if any(iface.find("model") is not None for iface in root.iter("interface")):
            result["protected_sections"].append("interface")

        if any(video.find("model") is not None for video in root.iter("video")):
            result["protected_sections"].append("video")

        return result

    @staticmethod
    def _registry_download_source(kind: str, data: dict) -> tuple:
        """The absolute URL and headers to fetch one registry entry from.

        ``url-isard`` is a path relative to the registry server, not a URL: it
        has to be joined to the configured server and carry the registration
        code, which is the build the engine's download thread used
        (``<url>/storage/<table>/<url-isard>``). ``url-web`` is the optional
        absolute alternate and needs neither. Shared so the media and domain
        branches cannot drift apart again — media used to hand the relative
        path straight to curl, which then resolved it as a hostname.
        """
        explicit = str(data.get("url") or "")
        if explicit.startswith(("http://", "https://")):
            return explicit, []
        url_isard = str(data.get("url-isard") or "")
        url_web = str(data.get("url-web") or "")
        if url_web and not url_isard:
            return url_web, []
        registry_url, code, _ = AdminDownloadsService._get_cfg()
        url = (
            f"{str(registry_url).rstrip('/')}/storage/{kind}/"
            f"{url_isard.lstrip('/')}"
        )
        return url, ([f"Authorization: {code}"] if code else [])

    @staticmethod
    def _kick_off_download_chain(
        kind: str,
        data: dict,
        pending_storage: Optional["Storage"] = None,
        insecure_ssl: bool = False,
    ) -> None:
        """Fire the storage RQ chain for a freshly inserted registry row.

        For ``media`` we delegate to the existing
        :meth:`Media.enqueue_download_chain`. For ``domains`` we use
        the new :meth:`Storage.enqueue_registry_download_chain_for_domain`
        which mirrors the chain shape but updates the desktop row
        instead of a media row. Skips the no-op cases (already-
        downloaded re-trigger, ISO-only desktops with no disk).
        """
        if kind == "media":
            from isardvdi_common.models.media import Media as RethinkMedia

            media_id = data.get("id")
            if not media_id:
                return
            try:
                media = RethinkMedia(media_id)
            except Exception:
                return
            url, headers = AdminDownloadsService._registry_download_source(
                "media", data
            )
            if not url or url.endswith("/"):
                return
            try:
                media.enqueue_download_chain(
                    user_id=data.get("user") or media.user,
                    url=url,
                    headers=headers,
                    insecure_ssl=insecure_ssl,
                )
            except Exception:
                # Best-effort: insert succeeded; surfaced via the media
                # row's stuck DownloadStarting status if the chain didn't
                # fire. Logged at apiv4 level by the route's outer try.
                raise

        elif kind == "domains":
            if pending_storage is None:
                # ISO-only desktop or already-downloaded re-trigger:
                # nothing to download.
                return
            full_url, headers = AdminDownloadsService._registry_download_source(
                "domains", data
            )
            pending_storage.enqueue_registry_download_chain_for_domain(
                domain_id=data["id"],
                url=full_url,
                headers=headers,
                insecure_ssl=insecure_ssl,
            )

    @staticmethod
    def _format_domains(data: list, user_id: str) -> list:
        """Format domain data for download insertion.

        Pure: no DB side effects. Storage allocation happens later in
        :meth:`_allocate_storage_for_pending_domain` (called from
        ``download_action`` after the row has been inserted), so the
        unit tests for this formatter don't need a live RethinkDB.
        """
        from isardvdi_common.helpers.helpers import Helpers
        from isardvdi_common.helpers.isard_viewer import default_guest_properties

        new_data = []
        for d in data:
            # Upstream registry carries disk bus in the sibling "hardware" field, not in create_dict. Capture before _get_domain_if_already_downloaded drops it.
            registry_disks = (d.get("hardware") or {}).get("disks") or []
            hints = AdminDownloadsService._parse_xml_protection_hints(
                decompress_xml(d.get("xml")) or ""
            )
            d = AdminDownloadsService._get_domain_if_already_downloaded(d, user_id)
            d["progress"] = {}
            d["status"] = "DownloadStarting"
            d.setdefault("guest_properties", default_guest_properties())
            d["detail"] = ""
            d["image"] = CardService.get_domain_stock_card(d["id"])
            d["accessed"] = int(time.time())
            d["hypervisors_pools"] = d["create_dict"]["hypervisors_pools"]
            interfaces = d["create_dict"]["hardware"]["interfaces"]
            # Tolerate already-normalized rows from
            # ``_get_domain_if_already_downloaded`` (each retry would
            # otherwise re-wrap dict entries into ``{"id": <dict>, "mac": …}``,
            # producing the triple-nested ``{"id": {"id": {"id": …}}}``
            # shape that breaks the rdb interfaces lookup).
            d["create_dict"]["hardware"]["interfaces"] = [
                (
                    interface
                    if isinstance(interface, dict) and "id" in interface
                    else {"id": interface, "mac": Helpers.gen_random_mac()}
                )
                for interface in interfaces
            ]
            disks = d["create_dict"]["hardware"].get("disks", [])
            bus = None
            if disks and disks[0].get("bus"):
                bus = disks[0]["bus"]
            elif registry_disks and registry_disks[0].get("bus"):
                bus = registry_disks[0]["bus"]
            if bus:
                d["create_dict"]["hardware"]["disk_bus"] = bus
            if hints["not_change_cpu_section"]:
                d["create_dict"]["hardware"]["not_change_cpu_section"] = True
            if hints["protected_sections"]:
                d["create_dict"]["xml_protected_sections"] = hints["protected_sections"]
            d["create_dict"]["hardware"]["qos_disk_id"] = False
            d["create_dict"]["reservables"] = {"vgpus": None}
            d["tag"] = False
            d["persistent"] = True
            d.pop("options", None)
            d.update(AdminDownloadsService._get_user_data(user_id))
            new_data.append(d)
        return new_data

    @staticmethod
    def _allocate_storage_for_pending_domain(
        data: dict, user_id: str
    ) -> Optional["Storage"]:
        """Allocate the ``Storage`` row that the registry download
        chain will write into and stamp ``storage_id`` + ``file`` on
        ``create_dict.hardware.disks[0]``.

        Returns the ``Storage`` instance (None for ISO-only desktops
        with no disks). Mutates ``data`` in place so the subsequent
        insert carries the storage references.
        """
        from isardvdi_common.models.storage import Storage

        if not data.get("create_dict", {}).get("hardware", {}).get("disks"):
            return None
        pending_storage = Storage.new_dict(
            user_id=user_id,
            pool_usage="desktop",
            parent_id=None,
        )
        pending_storage.status_logs = [{"time": int(time.time()), "status": "created"}]
        data["create_dict"]["hardware"]["disks"][0].update(
            {
                "storage_id": pending_storage.id,
                "file": pending_storage.path,
            }
        )
        return pending_storage

    @staticmethod
    def _format_medias(data: list, user_id: str) -> list:
        """Format media data for download insertion."""
        new_data = []
        for d in data:
            d = AdminDownloadsService._get_media_if_already_downloaded(d, user_id)
            d.update(AdminDownloadsService._get_user_data(user_id))
            d["progress"] = {}
            d["status"] = "DownloadStarting"
            d["accessed"] = int(time.time())
            # The download chain refuses to enqueue without an absolute
            # destination, and a registry entry carries no path of its own. The
            # by-URL path resolves one before inserting; do the same here, from
            # the row's own id so the file is named like every other media.
            if not d.get("path_downloaded"):
                from isardvdi_common.models.media import Media as RethinkMedia

                _pool, d["path_downloaded"] = RethinkMedia.resolve_download_path(
                    user_id=user_id,
                    category_id=d["category"],
                    media_id=d["id"],
                    kind=d["kind"],
                )
            new_data.append(d)
        return new_data

    @staticmethod
    def _get_domain_if_already_downloaded(data: dict, user_id: str) -> dict:
        """Check if a domain was already downloaded."""
        dbb = DownloadsProcessed.find_user_kind_by_url(
            "domains", user_id, data.get("url-isard")
        )
        d = dbb[0] if dbb else data
        for key in (
            "hardware",
            "xml_to_start",
            "hardware_from_xml",
            "force_update",
            "last_hyp_id",
        ):
            d.pop(key, None)
        return d

    @staticmethod
    def _get_media_if_already_downloaded(data: dict, user_id: str) -> dict:
        """Check if media was already downloaded."""
        dbb = DownloadsProcessed.find_user_kind_by_url(
            "media", user_id, data.get("url-isard")
        )
        if not dbb:
            dbb = DownloadsProcessed.find_user_kind_by_url_web(
                "media", user_id, data.get("url-web")
            )
        if not dbb:
            return data
        return dbb[0]

    @staticmethod
    def _get_user_data(user_id: str) -> dict:
        """Get user metadata for download records."""
        user = DownloadsProcessed.get_user_metadata(user_id)
        return {
            "user": user["id"],
            "username": user["username"],
            "category": user["category"],
            "group": user["group"],
        }
