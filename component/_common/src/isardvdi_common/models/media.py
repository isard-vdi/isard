#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

from typing import List, Literal, Optional
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib import queue_coverage, queue_tiers
from isardvdi_common.lib.storage.storage_pools.paths import build_category_pool_dir
from isardvdi_common.lib.task_index import MEDIA, current_task_id
from isardvdi_common.models.storage_pool import StoragePool
from pydantic import BaseModel, Field
from rethinkdb import r

from ..schemas.media import MediaStatusEnum
from ..schemas.shared.allowed import Allowed
from .task import Task


class MediaModel(BaseModel):
    accessed: float
    allowed: Allowed
    category: str
    description: str
    detail: str
    group: str
    hypervisors_pools: list[str]
    icon: str
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    name: str
    path: str
    path_downloaded: str
    progress: dict
    status: str
    url_isard: bool | str = Field(alias="url-isard")
    url_web: bool | str = Field(alias="url-web")
    user: str
    username: str


class Media(RethinkCustomBase):
    """
    Manage Media Objects

    Use constructor with keyword arguments to create new Media Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Media Object.
    """

    _rdb_table = "media"

    def create_task(self, *args, **kwargs):
        """
        Create Task for a Media.
        """
        # Phase-1 queue tiering (see isardvdi_common.lib.queue_tiers): route the
        # media download / delete / existence-check tasks onto the canonical
        # tiers. A media download defaults to background; delete/check resolve to
        # interactive by their action. The fair tiers are segmented by the media's
        # owning category (``self.category`` is the category id field) so the
        # elastic worker fair-schedules per tenant. A null category (system or
        # ownerless media) resolves to the NULL_CATEGORY sentinel lane.
        category = self.category or queue_tiers.NULL_CATEGORY
        kwargs.setdefault("category_id", category)
        kwargs.setdefault("media_id", self.id)
        kwargs.setdefault("index_owners", [self.id])
        kwargs.setdefault("index_kind", "media")
        if "queue" in kwargs:
            kwargs["queue"] = queue_tiers.retier_queue(
                kwargs["queue"], kwargs.get("task"), category
            )
        queue_tiers.retier_dependents(kwargs.get("dependents"), category)
        # Same producer-side gate as Storage.create_task: mandatory no-consumer
        # fail-fast (any tier, category-scoped) + mandatory foreground overload.
        queue_coverage.enforce_shed(Task._redis, kwargs)
        if "blocking" in kwargs:
            blocking = kwargs.pop("blocking")
        else:
            blocking = True
        # The index, not the row's scalar: the field is never cleared, so a
        # media whose job expired long ago would be refused work forever.
        pending_task = current_task_id(Task._redis, self.id, kind=MEDIA)
        if (
            blocking
            and pending_task
            and Task.exists(pending_task)
            and Task(pending_task).pending
        ):
            raise Error(
                "precondition_required",
                f"Media {self.id} has the pending task {pending_task}",
                description_code="media_pending_task",
            )
        return Task(*args, **kwargs).id

    def delete_file(self, user_id=None, keep_status=None):
        """Delete the media file and settle the row.

        Ordered so nothing is mutated before the last thing that can
        raise: a refused delete used to leave the row at ``maintenance``
        with no task behind it, which is a media nobody can delete
        afterwards.
        """
        if self.status in ("DownloadStarting", "Downloading", "Download"):
            raise Error(
                "precondition_required",
                f"Media {self.id} is downloading; abort the download first.",
                description_code="media_should_not_be_downloading",
            )
        if self.status == "deleted":
            return None
        if not self.path_downloaded:
            # A row without a path never had a file: the download chain
            # refuses to start without one, and the path is where curl
            # would have written.
            self.status = "deleted"
            return None
        pending_task = current_task_id(Task._redis, self.id, kind=MEDIA)
        if pending_task and Task.exists(pending_task) and Task(pending_task).pending:
            raise Error(
                "precondition_required",
                f"Media {self.id} has the pending task {pending_task}",
                description_code="media_pending_task",
            )

        queue = (
            f"storage.{StoragePool.get_best_for_action('delete', path=self.path_downloaded.rsplit('/', 1)[0]).id}"
            ".default"
        )
        previous_status = self.status
        # Every status that reaches here owns a file, so all of them get a
        # real delete task. Short-circuiting the failed ones to "deleted"
        # left their file on disk.
        finished_status = previous_status if keep_status else "deleted"
        recovery_status = (
            previous_status
            if previous_status in ("Downloaded", "DownloadFailed")
            else "Downloaded"
        )
        self.status = "maintenance"
        try:
            task_id = self.create_task(
                user_id=user_id,
                queue=queue,
                task="delete",
                blocking=False,
                job_kwargs={
                    "kwargs": {
                        "path": self.path_downloaded,
                    },
                },
                dependents=[
                    {
                        "queue": "core",
                        "task": "update_status",
                        "job_kwargs": {
                            "kwargs": {
                                "statuses": {
                                    "finished": {
                                        finished_status: {
                                            "media": [self.id],
                                        },
                                    },
                                    "failed": {
                                        recovery_status: {"media": [self.id]},
                                    },
                                    "canceled": {
                                        recovery_status: {
                                            "media": [self.id],
                                        },
                                    },
                                },
                            },
                        },
                    }
                ],
            )
        except Exception:
            self.status = previous_status
            raise
        return task_id

    @classmethod
    def resolve_download_path(cls, user_id, category_id, media_id, kind):
        """Compute the absolute filesystem path to download a media into.

        The media file is stored FLAT by its id -- ``<base_dir>/<media_id>.<kind>``
        -- exactly like main (``/isard/media/<id>.<kind>``) and like
        :class:`Storage` names its disks by id. The pool layout owns category
        placement: the default pool has no per-category subdir; a category pool
        inserts the category via ``build_category_pool_dir`` (legacy
        ``<mp>/<cat>/media`` or the ``{category}`` token). The human
        ``cat/group/provider/user/name`` label is NOT part of the on-disk path --
        it lives only in the media ``path`` field.

        :param user_id: The owner of the media (drives pool selection).
        :param category_id: The user's category id (used in non-default
            pool path layout, mirroring
            ``Storage.path_in_pool``).
        :param media_id: The media row id; used as the flat on-disk file name.
        :param kind: ``iso`` / ``floppy`` / ``qcow2`` (used as extension).
        :return: Tuple ``(pool, absolute_path)``.
        """
        pool = StoragePool.get_by_user_kind(user_id, "media")
        usage_path = pool.get_usage_path("media")
        if pool.id == DEFAULT_STORAGE_POOL_ID:
            base_dir = f"{pool.mountpoint}/{usage_path}"
        else:
            base_dir = build_category_pool_dir(pool.mountpoint, category_id, usage_path)
        return pool, f"{base_dir}/{media_id}.{kind}"

    def enqueue_download_chain(
        self,
        user_id,
        url,
        headers=None,
        insecure_ssl=False,
        google_drive_cookie=None,
        priority="low",
        retry: int = 0,
    ):
        """Enqueue the chain that downloads this media via isard-storage.

        Replaces the engine's SSH-curl ``DownloadThread`` flow. The
        ``download_url`` task is dispatched to the user's media pool
        worker on a *low priority* queue so concurrent disk creation
        keeps precedence. Status transitions:

            queued       → DownloadStarting (set by caller before enqueue)
            running      → Downloading      (flipped inside download_url)
            finished     → Downloaded       (dependent update_status)
            failed/canceled → DownloadFailed (dependent update_status)

        Cancellation: ``Task(self.task).cancel()`` publishes the generic
        ``task:cancel:<task_id>`` pub/sub signal that ``download_url``'s
        :class:`TaskCancelWatcher` listens to. apiv4's
        ``abort_media_download`` is just that one call.

        :return: Root task id.
        """
        if not self.path_downloaded:
            raise Error(
                "precondition_required",
                f"Media {self.id} has no path_downloaded; cannot enqueue download.",
                description_code="media_no_path",
            )
        pool = StoragePool.get_best_for_action(
            "download", path=self.path_downloaded.rsplit("/", 1)[0]
        )
        if pool is None:
            raise Error(
                "precondition_required",
                f"No storage pool found for media {self.id}",
                description_code="media_no_pool",
            )

        download_kwargs = {
            "media_id": self.id,
            "url": url,
            "dest_path": self.path_downloaded,
            "headers": list(headers or []),
            "insecure_ssl": bool(insecure_ssl),
            "google_drive_cookie": google_drive_cookie,
        }

        return self.create_task(
            user_id=user_id,
            queue=f"storage.{pool.id}.{priority}",
            task="download_url",
            retry=retry,
            retry_intervals=15,
            job_kwargs={"kwargs": download_kwargs},
            dependents=[
                {
                    "queue": "core",
                    "task": "media_update",
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "media_download_update_status",
                            "job_kwargs": {
                                "kwargs": {
                                    "media_id": self.id,
                                },
                            },
                        }
                    ],
                }
            ],
        )

    def check_existence(self, user_id=None):
        """From api/libv2/api_media media_task_check()"""
        if not self.path_downloaded:
            self.status = "deleted"
            return

        return self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('check_media_existence', path=self.path_downloaded.rsplit('/', 1)[0]).id}.default",
            task="check_media_existence",
            job_kwargs={
                "kwargs": {
                    "media_id": self.id,
                    "path": self.path_downloaded,
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "media_update",
                }
            ],
        )

    @classmethod
    def get_user_allowed_media(
        cls,
        user_id: str,
        user_category: str,
        user_group: str,
        user_role: str,
        start_after: str | int = None,
        page_size: int = 20,
        sort_order: str = "desc",
        index: str = "status_accessed",
        index_value: List = [MediaStatusEnum.downloaded.value],
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
    ) -> List[dict]:

        # Use the generic allowed items filter from Helpers
        build_shared_media_filter = Alloweds.build_shared_items_filter(
            user_role=user_role,
            user_category=user_category,
            user_group=user_group,
            user_id=user_id,
            consider_user_role=True,
        )

        # Combine with additional filters if provided
        combined_filters = None
        if filters:

            def combined_filter_func(media):
                return r.and_(
                    build_shared_media_filter(media),
                    filters(media) if callable(filters) else filters,
                )

            combined_filters = combined_filter_func
        else:
            combined_filters = build_shared_media_filter

        rows = cls.query_paginated_raw(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=combined_filters,
            pluck=[
                "id",
                "name",
                "description",
                "category",
                "group",
                "accessed",
                "user",
                "username",
                "kind",
                "status",
                "progress",
            ],
            merge_fn=lambda media: {
                "category_name": r.table("categories")
                .get(media["category"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
                "group_name": r.table("groups")
                .get(media["group"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
                "user_name": r.table("users")
                .get(media["user"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
            },
        )

        total = cls.query_count_raw(
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=combined_filters,
        )

        return {
            "rows": rows,
            "total": total,
        }
