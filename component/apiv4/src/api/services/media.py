#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

import os
import re
import time
from urllib.parse import quote, urlparse
from uuid import uuid4

import requests
from api.services.error import Error
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.media.media import MediaProcessed as CommonMedia
from isardvdi_common.models.media import Media as RethinkMedia
from isardvdi_common.models.media import MediaModel
from isardvdi_common.models.task import Task
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.schemas.media import MediaStatusEnum
from rethinkdb import r

# When True, the storage download_url task passes ``-k`` to curl.
# The legacy engine path hardcoded this to True; we default to the
# same value so existing deployments keep downloading from upstreams
# with self-signed certs without operator action. Set to ``false`` to
# enforce strict TLS validation.
URL_DOWNLOAD_INSECURE_SSL = (
    os.environ.get("URL_DOWNLOAD_INSECURE_SSL", "true").lower() == "true"
)


class MediaService:

    @staticmethod
    def get_media(media_id):
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )
        return CommonMedia.get_info(media_id)

    @staticmethod
    def get_user_media(user_id):
        """Get all media owned by a user."""
        return CommonMedia.get_user_media(user_id)

    @staticmethod
    def get_user_shared_media(payload):
        """Get all media shared with a user."""
        if not RethinkUser.exists(payload["user_id"]):
            raise Error(
                "not_found",
                f"User with ID {payload['user_id']} not found.",
                description_code="not_found",
            )

        return Alloweds.get_items_allowed(
            payload,
            table=RethinkMedia._rdb_table,
            query_pluck=[
                "id",
                "name",
                "status",
                "category",
                "group",
                "owner",
                "progress",
                "user",
                "description",
                "kind",
                "icon",
                "url-isard",
                "url-web",
                "accessed",
            ],
            query_filter=r.row["status"].ne("deleted"),
            order="name",
            only_in_allowed=True,
        )

    @staticmethod
    def get_media_allowed(media_id: str, category_id: str):
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )
        return {
            "selected": RethinkMedia.get(media_id)["allowed"],
            "available_groups": Alloweds.get_allowed_groups(category_id),
        }

    @staticmethod
    def get_media_desktops(media_id):
        return CommonMedia.get_desktops_with_media(media_id)

    @staticmethod
    def list_desktop_attached_media(desktop_id):
        """Return media attached to a desktop's create_dict.hardware."""
        return CommonMedia.list_domain_attached_media(desktop_id)

    @staticmethod
    def check_media_existence(media_id: str, user_id: str) -> dict | None:
        """Trigger a background task to verify a media file on disk.

        Ports v3 ``api_media.media_task_check``. If the media is not marked
        as ``downloaded`` the status is forced to ``deleted``; otherwise an
        RQ ``check_media_existence`` task is enqueued against the storage
        pool responsible for the downloaded path.
        """
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )
        media = RethinkMedia(media_id)
        task = media.check_existence(user_id=user_id)
        if task is None:
            return None
        # ``check_existence`` returns ``self.task`` which may already be a
        # plain dict-compatible object (see RethinkMedia); just make sure
        # the caller gets JSON-serialisable data.
        try:
            return task if isinstance(task, dict) else {"task_id": str(task)}
        except Exception:
            return None

    @staticmethod
    def change_owner(payload: dict, media_id: str, new_user_id: str) -> None:
        """Reassign a media item to a different user.

        Mirrors v3 ``api_v3_media_change_owner``
        (``api/views/CommonView.py:214``). Both ``ownsUserId`` and
        ``ownsMediaId`` are enforced before the DB flip.
        """
        Helpers.owns_user_id(payload=payload, user_id=new_user_id)
        Helpers.owns_media_id(payload=payload, media_id=media_id)
        Helpers.change_owner_media(user_id=new_user_id, media_id=media_id)

    @staticmethod
    def delete_media(media_id, payload):
        """Delete a media item."""
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )

        CommonMedia.remove_from_desktops(media_id)

        return RethinkMedia(media_id).delete_file(payload.get("user_id"))

    @staticmethod
    def get_user_allowed_media(
        user_id: str,
        user_category: str,
        user_group: str,
        user_role: str,
        start_after=None,
        page_size=10,
        sort_field="accessed",
        sort_order="desc",
        search=None,
        search_field=None,
        filters=None,
    ):
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )

        if sort_field == "accessed":
            # Admin users can access all templates, ignoring if enabled or not
            index = "status_accessed"
        index_value = [MediaStatusEnum.downloaded.value]

        return RethinkMedia.get_user_allowed_media(
            user_id=user_id,
            user_category=user_category,
            user_group=user_group,
            user_role=user_role,
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
        )

    @staticmethod
    def create_media(media_data, payload):
        """Create a new media item."""
        # Validate URL format
        url_str = str(media_data.url)
        quoted_url = quote(url_str, safe=":/?=&%")
        url = urlparse(quoted_url)

        if url.scheme != "https" or not re.compile(
            r"^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|"
            r"([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|"
            r"([a-zA-Z0-9][-_.a-zA-Z0-9]{0,61}[a-zA-Z0-9]))\."
            r"([a-zA-Z]{2,13}|[a-zA-Z0-9-]{2,30}.[a-zA-Z]{2,3})$"
        ).match(url.netloc):
            raise Error(
                "bad_request",
                "The URL does not meet the requirements.",
                description_code="media_url_bad_format",
            )

        from isardvdi_common.helpers.url_validation import validate_url_not_internal

        try:
            validate_url_not_internal(quoted_url)
        except ValueError as e:
            # validate_url_not_internal is framework-agnostic so it
            # raises plain ValueError. Convert to a typed 400 so the
            # admin sees "URL resolves to internal address" instead of
            # a generic 500. Same fix as the login_config helper applied
            # in the validate_url_scheme sweep.
            raise Error(
                "bad_request",
                str(e),
                description_code="media_url_internal",
            )

        # Probe the source URL to confirm it's reachable and learn the
        # advertised size. We use ``requests.get(stream=True)`` so the
        # body is never downloaded — we just read response headers and
        # close. Both the primary and the Mozilla-UA retry carry an
        # explicit ``timeout`` to bound how long the apiv4 worker can
        # wait on a remote server: the previous urllib retry passed no
        # timeout at all, which wedged the entire async event loop the
        # one time archive.org stalled mid-handshake.
        _MOZILLA_UA = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/35.0.1916.47 Safari/537.36"
        )
        try:
            probe = requests.get(
                quoted_url, stream=True, allow_redirects=True, timeout=30
            )
            if probe.status_code == 404:
                raise Error(
                    "not_found",
                    "The URL could not be found.",
                    description_code="media_url_not_found",
                )
            if probe.status_code >= 400:
                # Some upstreams 403 on the default UA; retry once with
                # a browser-style UA before declaring the URL unreachable.
                probe.close()
                probe = requests.get(
                    quoted_url,
                    stream=True,
                    allow_redirects=True,
                    timeout=30,
                    headers={"User-Agent": _MOZILLA_UA},
                )
            if probe.status_code >= 400:
                probe.close()
                raise Error(
                    "bad_request",
                    "The URL is not valid or accessible.",
                    description_code="media_url_not_valid",
                )
            content_length = probe.headers.get("Content-Length")
            probe.close()
        except Error:
            raise
        except requests.RequestException:
            raise Error(
                "bad_request",
                "The URL is not valid or accessible.",
                description_code="media_url_not_valid",
            )

        media_size = float(content_length) if content_length else 0

        Quotas.media_create(payload["user_id"], media_size)

        if not RethinkUser.exists(payload["user_id"]):
            raise Error(
                "not_found",
                f"User with ID {payload['user_id']} not found.",
            )
        user = RethinkUser.get(payload["user_id"])

        Helpers.check_duplicate(
            item_table="media",
            item_name=media_data.name,
            user=payload["user_id"],
            ignore_deleted=True,
        )

        username = user["username"]
        uid = user["uid"]

        urlpath = (
            payload["category_id"]
            + "/"
            + payload["group_id"]
            + "/"
            + payload["provider"]
            + "/"
            + uid
            + "-"
            + username
            + "/"
            + media_data.name.replace(" ", "_")
        )

        # Resolve the absolute destination path under the user's media
        # storage pool *before* inserting the row so the download task
        # has it from the start. Replaces the engine's
        # ``get_path_to_disk(type_path="media")`` plumbing.
        _pool, dest_path = RethinkMedia.resolve_download_path(
            user_id=payload["user_id"],
            category_id=payload["category_id"],
            relative_path=urlpath,
            kind=media_data.kind.value,
        )

        media_dict = {
            "name": media_data.name,
            "description": media_data.description,
            "user": payload["user_id"],
            "username": username,
            "category": payload["category_id"],
            "group": payload["group_id"],
            "url": str(media_data.url),
            "url-web": str(media_data.url),
            "kind": media_data.kind.value,
            "hypervisors_pools": (
                media_data.hypervisors_pools
                if media_data.hypervisors_pools
                else ["default"]
            ),
            "allowed": media_data.allowed.model_dump(),
            "status": "DownloadStarting",
            "progress": {
                "received": "0",
                "received_percent": 0,
                "speed_current": "",
                "speed_download_average": "",
                "speed_upload_average": "",
                "time_left": "",
                "time_spent": "",
                "time_total": "",
                "total": "",
                "total_percent": 0,
                "xferd": "0",
                "xferd_percent": "0",
            },
            "path": urlpath,
            "url-isard": False,
            "accessed": int(time.time()),
            "icon": "fa-circle-o",
            "path_downloaded": dest_path,
            "detail": "",
        }

        media_model = MediaModel(**media_dict)
        media = media_model.model_dump(mode="json", by_alias=True)

        RethinkMedia.insert_document(media)

        # Kick off the download chain on isard-storage's low-priority
        # queue. The chain handles status transitions
        # (Downloading → Downloaded / DownloadFailed) and progress
        # writes back to the media row.
        RethinkMedia(media_model.id).enqueue_download_chain(
            user_id=payload["user_id"],
            url=str(media_data.url),
            insecure_ssl=URL_DOWNLOAD_INSECURE_SSL,
        )

        return media_model.id

    def update_media_allowed(media_id: str, allowed):
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )
        Alloweds.update_table_item_allowed(
            table="media",
            item_id=media_id,
            allowed=allowed,
        )

    @staticmethod
    def abort_media_download(media_id: str):
        """Abort a media download.

        Sets the media row to ``DownloadAborting`` (back-up signal for
        the storage task's ``initial_check``) and asks the running task
        to cancel via the generic pub/sub primitive
        (``Task.cancel()`` publishes ``task:cancel:<id>``). The
        ``download_url`` task's :class:`TaskCancelWatcher` notices
        within ~500 ms, kills curl, deletes the partial file and
        raises; the dependent ``update_status`` then flips the row to
        ``DownloadFailed``.
        """
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )

        media = RethinkMedia(media_id)

        allowed_statuses = [
            MediaStatusEnum.downloading.value,
            MediaStatusEnum.download_starting.value,
            MediaStatusEnum.download.value,
        ]
        if media.status not in allowed_statuses:
            raise Error(
                "bad_request",
                f"Cannot abort download for media in status '{media.status}'. "
                f"Only allowed for statuses: {', '.join(allowed_statuses)}",
                description_code="media_status_invalid_for_abort",
            )

        # Persistent flag: covers the publish-before-subscribe race in
        # ``download_url``'s initial_check. The pub/sub signal is the
        # primary mechanism once the watcher is live.
        media.status = MediaStatusEnum.download_aborting.value

        if media.task and Task.exists(media.task):
            try:
                Task(media.task).cancel()
            except Exception:
                # cancel() best-effort: row flag still drives the
                # initial_check on the worker side, and the dependent
                # update_status will finalize the row when curl exits.
                pass

    @staticmethod
    def start_media_download(media_id: str):
        """(Re-)start a media download.

        Used to retry a previously failed download. Resets the row to
        ``DownloadStarting`` and enqueues a fresh chain — the user has
        already accepted that any partial file from the previous
        attempt was unusable.
        """
        if not RethinkMedia.exists(media_id):
            raise Error(
                "not_found",
                f"Media with ID {media_id} not found.",
            )

        media = RethinkMedia(media_id)

        allowed_statuses = [
            MediaStatusEnum.download.value,
            MediaStatusEnum.download_failed.value,
            # Allow retrying after an aborted/invalid-format download
            # too — same UX as legacy engine path.
            MediaStatusEnum.download_failed_invalid_format.value,
        ]
        if media.status not in allowed_statuses:
            raise Error(
                "bad_request",
                f"Cannot start download for media in status '{media.status}'. "
                f"Only allowed for statuses: {', '.join(allowed_statuses)}",
                description_code="media_status_invalid_for_start",
            )

        media.status = MediaStatusEnum.download_starting.value
        # Reset progress so the UI doesn't show stale percentages.
        media.progress = {
            "received": "0",
            "received_percent": 0,
            "speed_current": "",
            "speed_download_average": "",
            "speed_upload_average": "",
            "time_left": "",
            "time_spent": "",
            "time_total": "",
            "total": "",
            "total_percent": 0,
            "xferd": "0",
            "xferd_percent": "0",
        }

        media.enqueue_download_chain(
            user_id=media.user,
            url=media.url,
            insecure_ssl=URL_DOWNLOAD_INSECURE_SSL,
        )
