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

from time import time
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from cachetools import cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.lib import queue_tiers
from isardvdi_common.lib.storage.storage_pools.paths import build_category_pool_dir
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.user import User
from pydantic import BaseModel, Field
from rethinkdb import r
from rq.job import JobStatus

from ..schemas.storage import *
from . import domain
from .task import Task

# Owner category is resolved on every storage-task produce; cache per user so a
# burst of produces for one owner does not re-hit rethinkdb.
_owner_category_cache = SynchronizedTTLCache(maxsize=4096, ttl=60)


@cached(_owner_category_cache)
def _owner_category(user_id):
    owner = User.get(user_id)
    return owner.get("category") if owner else None


class StorageModel(BaseModel):
    usage: str
    storage_type: Literal["qcow2", "vmdk"] = "qcow2"
    parent: Optional[str]
    size: str
    user_id: Optional[str] = None
    perms: List[Literal["r", "w"]]
    directory_path: str
    qemu_img_info: Optional[QemuImgInfo] = None
    status: str
    status_logs: List[Dict[str, Any]] = []
    status_time: Optional[float]
    task: Optional[str]
    type: Literal["qcow2", "vmdk"]
    id: str = Field(default_factory=lambda: str(uuid4()))


def get_storage_id_from_path(path):
    """
    Get Storage ID from path.

    :param path: Path of storage
    :type path: str
    :return: Storage ID
    :rtype: str
    """
    return path.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def get_queue_from_storage_pools(storage_pool_origin, storage_pool_destination):
    if storage_pool_origin == storage_pool_destination:
        queue = storage_pool_origin.id
    else:
        storage_pool_ids = [storage_pool_origin.id, storage_pool_destination.id]
        storage_pool_ids.sort()
        queue = ":".join(storage_pool_ids)
    return queue


def new_storage_directory_path(user_id, pool_usage):
    """
    Create a new storage path.

    :param user_id: User ID
    :type user_id: str
    :param pool_usage: Storage pool_usage: desktop or template
    :type pool_usage: str
    """
    storage_pool = StoragePool.get_by_user_kind(user_id, pool_usage)
    if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
        return f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(pool_usage)}"
    # A non-default (category) pool nests disks under the owner's category. If
    # the owner is gone the previous code fell through and returned None, which
    # produced a "None/<id>.qcow2" path on disk. Fail loudly instead.
    if not User.exists(user_id):
        raise Exception(
            "precondition_required",
            f"Cannot resolve storage path: user {user_id} does not exist",
        )
    category = User(user_id).category
    if not category:
        raise Exception(
            "precondition_required",
            f"Cannot resolve storage path: user {user_id} has no category",
        )
    return build_category_pool_dir(
        storage_pool.mountpoint, category, storage_pool.get_usage_path(pool_usage)
    )


class Storage(RethinkCustomBase):
    """
    Manage Storage Objects

    Use constructor with keyword arguments to create new Storage Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Storage Object.
    """

    _rdb_table = "storage"

    @classmethod
    def new_dict(cls, user_id, pool_usage, parent_id=None, format="qcow2") -> "Storage":
        """
        Create a new storage dictionary.

        :param user_id: User ID
        :type user_id: str
        :param pool_usage: Storage pool_usage: desktop or template
        :type pool_usage: str
        :param parent_id: Parent ID
        :type parent_id: str
        """
        if parent_id and not cls.exists(parent_id):
            raise Exception(
                "precondition_required",
                f"Parent {parent_id} does not exist",
            )

        storage_dict = {
            "id": str(uuid4()),
            "type": format,
            "directory_path": new_storage_directory_path(user_id, pool_usage),
            "parent": parent_id,
            "user_id": user_id,
            "status": "non_existing",
            "perms": ["r", "w"] if pool_usage == "desktop" else ["r"],
            "status_logs": [],
        }

        return Storage.init_document(**storage_dict)

    @classmethod
    def get_from_task_id(cls, task_id):
        """
        Get storage from task ID.

        :param task_id: Task ID
        :type task_id: str
        :return: Storage object
        :rtype: isardvdi_common.storage.Storage
        """
        with cls._rdb_context():
            storage_id = list(
                r.table(cls._rdb_table)
                .get_all(task_id, index="task")["id"]
                .run(cls._rdb_connection)
            )

        match len(storage_id):
            case 0:
                return None
            case 1:
                return cls(storage_id[0])
            case _:
                print("WARNING: More than one storage found for task_id", task_id)
                return cls(storage_id[0])

    @classmethod
    def get_storage_ids_from_task_ids(cls, task_ids):
        with cls._rdb_context():
            task_storage_map = list(
                r.db("isard")
                .table("storage")
                .get_all(r.args(task_ids), index="task")
                .map(
                    lambda doc: {
                        "task_id": doc["task"],
                        "storage_id": doc["id"],
                    }
                )
                .run(cls._rdb_connection)
            )

        return task_storage_map

    @property
    def path(self):
        """
        Returns the path of storage.
        """
        return f"{self.directory_path}/{self.id}.{self.type}"

    @property
    def pool(self):
        """
        Returns the storage pool of storage.
        """
        pools = StoragePool.get_by_path(self.directory_path)
        if not pools:
            # get_by_path already falls back to the default pool, so this only
            # triggers in the degenerate case where even the default pool row is
            # missing. Return the default pool object instead of crashing on an
            # empty-list [0] index (which broke every operation on a disk whose
            # pool had been removed).
            return StoragePool(DEFAULT_STORAGE_POOL_ID)
        return pools[0]

    @property
    def pool_usage(self):
        """
        Returns the storage pool usage of storage.
        """
        return self.pool.get_usage_by_path(self.directory_path)

    def _require_category(self):
        """
        Return the owner's category or raise if it cannot be resolved.

        Non-default pools nest disks under the owner's category. A missing
        category (deleted owner) would otherwise produce a literal
        "<mountpoint>/None/..." path, so fail loudly instead.
        """
        category = self.category
        if not category:
            raise Exception(
                "precondition_required",
                f"Cannot resolve storage path: storage {self.id} owner has no category",
            )
        return category

    def path_in_pool(self, storage_pool):
        """
        Map storage path to Storage Pool path.

        :param storage: Storage object
        :type storage: Storage
        :return: Path
        :rtype: str
        """
        if self.pool_usage is None:
            return None
        if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
            return f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(self.pool_usage)}/{self.id}.{self.type}"
        directory = build_category_pool_dir(
            storage_pool.mountpoint,
            self._require_category(),
            storage_pool.get_usage_path(self.pool_usage),
        )
        return f"{directory}/{self.id}.{self.type}"

    def directory_path_as_usage(self, usage):
        """
        Returns the path of storage if it was used as the given usage.

        :param usage: The usage to be used
        :type usage: str
        """
        if usage not in ["desktop", "template"]:
            raise Exception(
                {
                    "error": "bad_request",
                    "description": f"Usage {usage} must be desktop or template",
                }
            )

        # Resolve usage from the directory, not self.path (which includes the
        # "<id>.<type>" filename). get_usage_by_path tolerates a trailing
        # filename now, but passing the directory makes the intent explicit and
        # avoids re-deriving a fresh random path when the usage already matches.
        if self.pool.get_usage_by_path(self.directory_path) == usage:
            return self.directory_path

        return new_storage_directory_path(self.user_id, usage)

    def set_storage_pool(self, storage_pool):
        """
        Change storage pool.

        :param storage_pool: Storage Pool object
        :type storage_pool: isardvdi_common.models.storage_pool.StoragePool
        """
        if self.pool == storage_pool:
            return
        if self.pool_usage is None:
            return None

        if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
            self.directory_path = f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(self.pool_usage)}"
        else:
            self.directory_path = build_category_pool_dir(
                storage_pool.mountpoint,
                self._require_category(),
                storage_pool.get_usage_path(self.pool_usage),
            )

    def get_storage_pool_path(self, storage_pool):
        """
        Get storage in pool.

        :param storage_pool: Storage Pool object
        :type storage_pool: isardvdi_common.models.storage_pool.StoragePool
        """
        if self.pool_usage is None:
            return None

        if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
            return f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(self.pool_usage)}"
        else:
            return build_category_pool_dir(
                storage_pool.mountpoint,
                self._require_category(),
                storage_pool.get_usage_path(self.pool_usage),
            )

    @property
    def children(self):
        """
        Returns the non-deleted storages that have this storage as parent.
        """
        return self.get_index(
            [self.id], index="parent", filter=lambda s: s["status"] != "deleted"
        )

    @property
    def derivatives(self):
        """
        Returns all the storages that have this storage as a parent,
        recursively including all descendant children (leaf nodes).
        NOTE: Does not include the storage itself.
        """
        # Get the direct children first
        direct_children = self.children

        # For each child, recursively get their children
        all_children = []
        for child in direct_children:
            all_children.append(child)
            # Recursively get children of the child
            all_children.extend(child.children)

        return all_children

    @property
    def parents(self):
        """
        Returns the storage parents hierarchy.

        A ``parent`` field that is missing from the storage table or whose
        value is not a UUID (e.g. a path string left over from older code
        paths) terminates the walk silently rather than raising — the chain
        on disk is still readable via the ``backing_file=`` link, but the
        parent object isn't available as a Storage instance.
        """
        if self.parent is None:
            return []
        if not Storage.exists(self.parent):
            return []
        parent_obj = Storage(self.parent)
        return [parent_obj] + parent_obj.parents

    @property
    def operational(self):
        """
        Returns True if the storage chain statuses are ready, otherwise False.
        """
        if self.parent is None:
            return True
        return all([storage.status == "ready" for storage in self.parents])

    @property
    def domains(self):
        """
        Returns the domains using this storage.
        """
        return domain.Domain.get_with_storage(self)

    @property
    def domains_derivatives(self):
        """
        Returns all domains attached to the storage and its descendants recursively.
        NOTE: Does not include the storage domains itself.
        """
        # First, get the domains attached to the current storage object
        storage_domains = self.domains

        # Recursively get all child storages
        all_children = self.children

        # For each child storage, add its domains to the list
        all_domains = []
        for child in all_children:
            all_domains.extend(child.domains)

        return all_domains

    @property
    def category(self):
        """The category of the storage owner (user_id), or None if the owner no
        longer exists. Cached per user (see ``_owner_category``); this is on the
        per-produce hot path."""
        return _owner_category(self.user_id)

    @classmethod
    def create_from_path(cls, path, user_id):
        """
        Create Storage from path.

        :param path: Path of storage
        :type path: str
        :param user_id: User ID of the storage owner
        :type user_id: str
        :return: Storage object
        :rtype: isardvdi_common.models.storage.Storage
        """
        return Storage.init_document(
            id=get_storage_id_from_path(path),
            type=path.rsplit(".", 1)[-1],
            directory_path=path.rsplit("/", 1)[0],
            status="ready",
            user_id=user_id,
            parent=None,
            perms=["r"],
            status_logs=[{"time": int(time()), "status": "created"}],
        )

    @classmethod
    def get_by_path(cls, path):
        """
        Get storage by path.

        :param path: Path of storage
        :type path: str
        :return: Storage object
        :rtype: isardvdi_common.models.storage.Storage
        """
        storage_id = get_storage_id_from_path(path)
        if cls.exists(storage_id):
            return cls(storage_id)

    @property
    def statuses(self):
        """
        Retrieve the status and IDs for a storage and its associated domain
        based on the provided storage ID.

        :param storage_id: The storage ID to filter by
        :return: A list of dictionaries with storage and domain statuses and IDs
        """
        return {
            "id": self.id,
            "status": self.status,
            "path": self.path,
            "pool": self.pool.id,
            "domains": [
                {
                    "id": domain.id,
                    "status": domain.status,
                    "kind": domain.kind,
                }
                for domain in self.domains
            ],
        }

    """
    Tasks
    """

    def create_task(self, *args, **kwargs):
        """
        Create Task for a Storage.
        """
        # Normalise the root task's queue and every dependent's queue to the tier
        # model, using each task's own ``action`` for the action-aware rules, and
        # thread the owning category so bulk/background land on the per-category
        # fair lanes the elastic worker schedules (the worker parses the category
        # back from the queue name). A None owner (deleted or system task)
        # resolves to the NULL_CATEGORY sentinel lane.
        category = self.category or queue_tiers.NULL_CATEGORY
        kwargs.setdefault("category_id", category)
        if "queue" in kwargs:
            kwargs["queue"] = queue_tiers.retier_queue(
                kwargs["queue"], kwargs.get("task"), category
            )
        queue_tiers.retier_dependents(kwargs.get("dependents"), category)
        if "blocking" in kwargs:
            blocking = kwargs.pop("blocking")
        else:
            blocking = True
        if (
            blocking
            and self.task
            and Task.exists(self.task)
            and Task(self.task).pending
        ):
            # Typed ``Error`` so the apiv4 route layer maps this to
            # 428 Precondition Required instead of swallowing the
            # raw ``Exception`` as a 500 Internal Server Error.
            raise Error(
                "precondition_required",
                f"Storage {self.id} has the pending task {self.task}",
                description_code="storage_pending_task",
            )
        try:
            self.task = Task(*args, **kwargs).id
        except Exception as e:
            raise

    def find(self, user_id, blocking=True, retry=3):
        """
        Create a task to find the storage.
        It assumes any isard-storage will have all mountpoints in /isard.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param blocking: Blocking
        :type blocking: bool
        :return: Task ID
        :rtype: str
        """

        self.create_task(
            blocking=blocking,
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('find', path=self.directory_path).id}.default",
            task="find",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_id": self.id,
                    "storage_path": self.path,
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update_pool",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update_parent",
                            "job_kwargs": {"kwargs": {"storage_id": self.id}},
                        }
                    ],
                }
            ],
        )
        return self.task

    def check_backing_chain(
        self, user_id, blocking=True, retry=3, priority="background"
    ):
        """
        Create a task to check the storage.

        The tier follows the TRIGGER, not the action: a standalone backing-chain
        refresh (post-stop size refresh, batch status re-scan) nobody is blocked
        on defaults to ``background`` (the idle lane); an admin datatable "check"
        click passes ``priority="standard"`` for a quicker turnaround. The user
        still sees the result — feedback is emitted regardless of tier.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param priority: Requested tier for the refresh (``background`` by default
            for idle lifecycle refreshes; ``standard`` for an admin-triggered one)
        :type priority: str
        :return: Task ID
        :rtype: str
        """

        self.create_task(
            blocking=blocking,
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info_backing_chain', path=self.directory_path).id}.{priority}",
            task="qemu_img_info_backing_chain",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_id": self.id,
                    "storage_path": self.path,
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                }
            ],
        )
        return self.task

    def set_maintenance(self, action="system maintenance"):
        """
        Set storage and it's domains to maintenance status.

        :param storage: Storage object
        :type storage: isardvdi_common.models.storage.Storage
        :param action: Action
        :type action: str
        """
        if action == "move":
            if self.status not in ["ready", "recycled"]:
                raise Exception(
                    "precondition_required",
                    f"Storage {self.id} can only be moved from 'ready' or 'recycled' status. Current status is '{self.status}'",
                    "storage_invalid_status_for_move",
                )
        elif self.status != "ready" and action not in (
            "create",
            "delete",
            "download",
        ):
            raise Exception(
                "precondition_required",
                f"Storage {self.id} must be Ready in order to operate with it. It's actual status is {self.status}",
                "storage_not_ready",
            )
        # "create" / "download" are fresh-storage actions — the domain
        # being wired in is the whole point, and by construction it is
        # not yet Stopped (it is in a Creating* / DownloadStarting
        # state) and the storage has no children. Skip the two
        # invariants that only apply to pre-existing storage.
        if action not in ("create", "download"):
            domains = self.domains
            if any(domain.status != "Stopped" for domain in domains):
                raise Exception(
                    "precondition_required",
                    f"Storage {self.id} must have all domains stopped in order to set it to maintenance. Some desktops are not stopped.",
                    "desktops_not_stopped",
                )
            if len(self.children) > 0:
                raise Exception(
                    "precondition_required",
                    f"Storage {self.id} has children storages that depend on it as backing file",
                    "storage_has_children",
                )
            for domain in self.domains:
                domain.current_action = action
                domain.status = "Maintenance"
        self.status = "maintenance"

    def set_ready(self):
        """
        Set storage and it's domains to ready status.
        """
        if self.status != "maintenance":
            raise Exception(
                "precondition_required",
                f"Storage {self.id} must be maintenance in order to return back to ready status. It's actual status is {self.status}",
                "storage_not_maintenance",
            )
        for domain in self.domains:
            domain.status = "Stopped"
            domain.current_action = None
        self.status = "ready"

    def rsync(
        self,
        user_id,
        destination_path,
        bwlimit=0,
        remove_source_file=True,
        priority="default",
        retry: int = 0,
        timeout=43200,  # (12 hours × 60 minutes/hour × 60 seconds/minute = 43,200 seconds)
    ):
        """
        Create a task to move the storage using rsync.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param destination_path: Destination path
        :type destination_path: str
        :param bwlimit: Bandwidth limit in KB/s
        :type bwlimit: int
        :param remove_source_file: Remove source file
        :type remove_source_file: bool
        :param priority: Priority
        :type priority: str
        :param timeout: Timeout
        :type timeout: int
        :return: Task ID
        :rtype: str
        """
        # Capture original status to preserve it after move
        original_status = self.status
        final_status = "recycled" if original_status == "recycled" else "ready"

        origin_path = self.path

        queue_rsync = f"storage.{get_queue_from_storage_pools(self.pool, StoragePool.get_best_for_action('move', destination_path))}.{priority}"
        queue_origin = f"storage.{StoragePool.get_best_for_action('move_delete', path=self.directory_path).id}.{priority}"
        self.set_maintenance("move")
        self.create_task(
            blocking=True,
            user_id=user_id,
            queue=queue_rsync,
            task="move",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "origin_path": self.path,
                    "destination_path": destination_path,
                    "method": "rsync",
                    "bwlimit": bwlimit,
                    "remove_source_file": remove_source_file,
                },
                "timeout": timeout,
            },
            dependents=(
                [
                    {
                        "queue": "core",
                        "task": "storage_update",
                        "job_kwargs": {
                            "kwargs": {
                                "id": self.id,
                                "status": final_status,
                                "directory_path": destination_path.split("/" + self.id)[
                                    0
                                ],
                                "qemu-img-info": {
                                    "filename": destination_path,
                                },
                            }
                        },
                        "dependents": [
                            {
                                "queue": "core",
                                "task": "update_status",
                                "job_kwargs": {
                                    "kwargs": {
                                        "statuses": {
                                            JobStatus.CANCELED: {
                                                original_status: {
                                                    "storage": [self.id],
                                                },
                                            },
                                            JobStatus.FAILED: {
                                                original_status: {
                                                    "storage": [self.id],
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        ],
                    },
                ]
                + (
                    [
                        {
                            "queue": queue_origin,
                            "task": "move_delete",
                            "job_kwargs": {
                                "kwargs": {
                                    "path": origin_path,
                                }
                            },
                        }
                    ]
                    if not remove_source_file
                    else []
                )
            ),
        )

        return self.task

    def mv(
        self,
        user_id,
        destination_path,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to move the storage using mv.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param destination_path: Destination path
        :type destination_path: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        origin_path = self.path

        queue_mv = f"storage.{get_queue_from_storage_pools(self.pool, StoragePool.get_best_for_action('move', destination_path))}.{priority}"

        self.set_maintenance("move")
        self.create_task(
            user_id=user_id,
            queue=queue_mv,
            task="move",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "origin_path": origin_path,
                    "destination_path": f"{destination_path}/{self.id}.{self.type}",
                    "method": "mv",
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                    "job_kwargs": {
                        "kwargs": {
                            "id": self.id,
                            "directory_path": destination_path,
                            "qemu-img-info": {
                                "filename": f"{destination_path}/{self.id}.{self.type}"
                            },
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "update_status",
                            "job_kwargs": {
                                "kwargs": {
                                    "statuses": {
                                        "_all": {
                                            "ready": {
                                                "storage": [self.id],
                                            },
                                            "Stopped": {
                                                "domain": [
                                                    domain.id for domain in self.domains
                                                ],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    ],
                },
            ],
        )

        return self.task

    def task_delete(
        self,
        user_id,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to delete the storage.
        This task will delete the storages but will not delete the domains.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        domains_to_failed = [domain.id for domain in self.domains]
        domains_to_failed.extend([domain.id for domain in self.domains_derivatives])
        self.set_maintenance("delete")
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('delete', path=self.directory_path).id}.{priority}",
            task="delete",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "path": self.path,
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "canceled": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                    "Stopped": {
                                        "domain": [
                                            domain.id for domain in self.domains
                                        ],
                                    },
                                },
                                # A failed delete surfaces to the consumer as
                                # job_status="failed" (a running-cancel raises,
                                # too). Mirror "canceled": restore the source to
                                # ready rather than fall through to "finished"
                                # (which drops the DB row while the file may
                                # still be on disk).
                                "failed": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                    "Stopped": {
                                        "domain": [
                                            domain.id for domain in self.domains
                                        ],
                                    },
                                },
                                "finished": {
                                    "deleted": {
                                        "storage": [self.id],
                                    },
                                    "orphan": {
                                        "storage": [
                                            storage.id for storage in self.derivatives
                                        ]
                                    },
                                    "Failed": {
                                        "domain": domains_to_failed,
                                    },
                                },
                            },
                        },
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_delete",
                            "job_kwargs": {"kwargs": {"storage_id": self.id}},
                        }
                    ],
                },
            ],
        )

        return self.task

    def increase_size(
        self,
        user_id,
        increment,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to increase the storage size.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param increment: Increment in GB
        :type increment: int
        :param priority: Priority
        :type priority: str
        """
        resize_queue = f"storage.{StoragePool.get_best_for_action('resize', path=self.directory_path).id}.{priority}"

        self.set_maintenance("resize")
        self.create_task(
            user_id=user_id,
            queue=resize_queue,
            task="resize",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {"storage_path": self.path, "increment": increment},
            },
            dependents=[
                {
                    "queue": f"storage.{StoragePool.get_best_for_action('resize').id}.{priority}",
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                        }
                    ],
                }
            ],
        )

        return self.task

    def virt_win_reg(
        self,
        user_id,
        registry_patch,
        priority="default",
        retry: int = 0,
        timeout=43200,  # (12 hours × 60 minutes/hour × 60 seconds/minute = 43,200 seconds)
    ):
        """
        Create a task to write a windows registry patch to the storage.
        This task will only work with storages that have Windows XP or newer installed.
        https://libguestfs.org/virt-win-reg.1.html

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param registry_patch: Windows registry patch
        :type registry_patch: str
        :param priority: Priority
        :type priority: str
        :param timeout: Timeout
        :type timeout: int
        :return: Task ID
        :rtype: str
        """
        queue_virt_win_reg = f"storage.{StoragePool.get_best_for_action('virt_win_reg', path=self.directory_path).id}.{priority}"

        self.set_maintenance("virt_win_reg")
        self.create_task(
            user_id=user_id,
            queue=queue_virt_win_reg,
            task="virt_win_reg",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_path": self.path,
                    "registry_patch": registry_patch,
                },
                "timeout": timeout,
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "finished": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                    "Stopped": {
                                        "domain": [
                                            domain.id for domain in self.domains
                                        ],
                                    },
                                },
                                "canceled": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                    "Stopped": {
                                        "domain": [
                                            domain.id for domain in self.domains
                                        ],
                                    },
                                },
                                # virt_win_reg is in-place; a failed merge
                                # surfaces as job_status="failed" (a cancel
                                # raises, too). Mirror "canceled"/"finished":
                                # leave the storage ready rather than the
                                # missing-branch no-op that only worked while
                                # the root was force-FINISHED.
                                "failed": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                    "Stopped": {
                                        "domain": [
                                            domain.id for domain in self.domains
                                        ],
                                    },
                                },
                            },
                        },
                    },
                },
            ],
        )

        return self.task

    def sparsify(
        self,
        user_id,
        priority="default",
        secondary_priority="default",
        retry: int = 0,
        timeout=43200,  # (12 hours × 60 minutes/hour × 60 seconds/minute = 43,200 seconds)
    ):
        """
        Create a task to sparsify the storage.
        https://libguestfs.org/virt-sparsify.1.html

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param priority: Priority
        :type priority: str
        :param secondary_priority: Priority for the backing chain task
        :type secondary_priority: str
        :param timeout: Timeout
        :type timeout: int
        :return: Task ID
        :rtype: str
        """
        queue_sparsify = f"storage.{StoragePool.get_best_for_action('sparsify', path=self.directory_path).id}.{priority}"
        # Use a different queue to avoid having to wait when launching in bulk
        queue_backing_chain = f"storage.{StoragePool.get_best_for_action('qemu_img_info_backing_chain', path=self.directory_path).id}.{secondary_priority}"

        self.set_maintenance("sparsify")
        self.create_task(
            user_id=user_id,
            queue=queue_sparsify,
            task="sparsify",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_path": self.path,
                },
                "timeout": timeout,
            },
            dependents=[
                {
                    "queue": queue_backing_chain,
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                        }
                    ],
                },
            ],
        )

        return self.task

    def disconnect_chain(
        self,
        user_id,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to disconnect the storage.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param priority: Priority
        :type priority: str
        """
        disconnect_queue = f"storage.{StoragePool.get_best_for_action('disconnect', path=self.directory_path).id}.{priority}"

        self.set_maintenance("disconnect")
        self.create_task(
            user_id=user_id,
            queue=disconnect_queue,
            task="disconnect",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_path": self.path,
                },
            },
            dependents=[
                {
                    "queue": disconnect_queue,
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_update_parent",
                                    "job_kwargs": {"kwargs": {"storage_id": self.id}},
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def convert(
        self,
        user_id,
        new_storage: "Storage",
        new_storage_type,
        new_storage_status,
        compress,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to convert the storage.

        Cancellation rides ``Task(self.task).cancel()``; ``run_with_progress``
        in the ``convert`` task body listens via :class:`TaskCancelWatcher`
        and SIGTERMs qemu-img mid-run. The terminal ``update_status``
        maps ``JobStatus.CANCELED`` to ``deleted`` for ``new_storage``.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param new_storage: New storage object
        :type new_storage: isardvdi_common.models.storage.Storage
        :param new_storage_type: New storage type. Supported formats: qcow2, vmdk
        :type new_storage_type: str
        :param new_storage_status: New storage status
        :type new_storage_status: str
        :param compress: Whether to compress the new storage or not
        :type compress: bool
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """

        self.set_maintenance("convert")
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('convert', path=self.directory_path).id}.{priority}",
            task="convert",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "source_disk_path": self.path,
                    "dest_disk_path": new_storage.path,
                    "format": new_storage_type.lower(),
                    "compression": compress,
                },
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "update_status",
                    "job_kwargs": {
                        "kwargs": {
                            "statuses": {
                                "_all": {
                                    "ready": {
                                        "storage": [self.id],
                                    },
                                },
                                "finished": {
                                    new_storage_status: {
                                        "storage": [new_storage.id],
                                    },
                                },
                                "canceled": {
                                    "deleted": {
                                        "storage": [new_storage.id],
                                    },
                                },
                                # A failed convert surfaces to the consumer as
                                # job_status="failed" (a running-cancel raises,
                                # too). Delete the half-written destination
                                # instead of leaving it at its target status —
                                # otherwise a partial/corrupt disk reads as a
                                # good one.
                                "failed": {
                                    "deleted": {
                                        "storage": [new_storage.id],
                                    },
                                },
                            }
                        }
                    },
                }
            ],
        )

        pass

    def recreate(
        self,
        user_id,
        domain_id,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to recreate the storage.
        This tasks will delete the current storage and create a new one with the same parent. The domains passed as argument will be updated to use the new storage.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param domain_id: Domain ID to update the storage
        :type domain_id: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        # recreate is a foreground op (fresh disk from the parent, then delete the
        # old one): route its default to the seconds ``standard`` lane, not the
        # sub-second reserved (interactive) pool a plain ``create`` would take. An
        # explicit non-default priority from the caller is still honoured.
        if priority == "default":
            priority = "standard"
        if not self.parent:
            raise Exception(
                "precondition_required",
                "Storage parent missing",
                "storage_has_no_parent",
            )

        if not self.operational:
            raise Exception(
                "precondition_required",
                "Storage parent not ready",
                "storage_parent_not_ready",
            )

        if not Storage.exists(self.parent):
            raise Exception(
                "precondition_required",
                "Storage parent missing",
                "storage_has_no_parent",
            )
        storage_parent = Storage(self.parent)
        parent_args = {
            "parent_path": storage_parent.path,
            "parent_type": storage_parent.type,
        }

        status_logs = self.status_logs
        status_logs.append({"time": int(time()), "status": f"recreated from {self.id}"})

        new_storage = Storage.new_dict(
            self.user_id,
            self.pool_usage,
            storage_parent.id,
        )
        new_storage.status_logs = status_logs

        new_storage_path = str(
            new_storage.directory_path + "/" + new_storage.id + "." + new_storage.type
        )

        self.set_maintenance("recreate")
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('create', new_storage.directory_path).id}.{priority}",
            task="create",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_path": new_storage_path,
                    "storage_type": new_storage.type,
                    **parent_args,
                },
            },
            dependents=[
                {
                    "queue": f"core",
                    "task": "domain_change_storage",
                    "job_kwargs": {
                        "kwargs": {
                            "domain_id": domain_id,
                            "storage_id": new_storage.id,
                        },
                    },
                    "dependents": [
                        {
                            "queue": f"storage.{StoragePool.get_best_for_action('qemu_img_info_backing_chain', new_storage.directory_path).id}.{priority}",
                            "task": "qemu_img_info_backing_chain",
                            "job_kwargs": {
                                "kwargs": {
                                    "storage_id": new_storage.id,
                                    "storage_path": new_storage_path,
                                }
                            },
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_update",
                                }
                            ],
                        },
                        {
                            "queue": f"storage.{StoragePool.get_best_for_action('delete', self.directory_path).id}.{priority}",
                            "task": "delete",
                            "job_kwargs": {
                                "kwargs": {
                                    "path": self.path,
                                }
                            },
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_delete",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "storage_id": self.id,
                                        }
                                    },
                                    "dependents": [
                                        {
                                            "queue": "core",
                                            "task": "update_status",
                                            "job_kwargs": {
                                                "kwargs": {
                                                    "statuses": {
                                                        "_all": {
                                                            "deleted": {
                                                                "storage": [self.id],
                                                            }
                                                        },
                                                        JobStatus.FAILED: {
                                                            new_storage.status: {
                                                                "storage": [
                                                                    new_storage.id
                                                                ],
                                                            },
                                                            "Failed": {
                                                                "domain": [
                                                                    domain.id
                                                                    for domain in new_storage.domains
                                                                ],
                                                            },
                                                        },
                                                        JobStatus.CANCELED: {
                                                            new_storage.status: {
                                                                "storage": [
                                                                    new_storage.id
                                                                ],
                                                            },
                                                            "Stopped": {
                                                                "domain": [
                                                                    domain.id
                                                                    for domain in new_storage.domains
                                                                ]
                                                            },
                                                        },
                                                    }
                                                }
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ],
        )

        return self.task

    @classmethod
    def create_new_storage(
        cls,
        user_id,
        pool_usage,
        parent_id,
        size,
        storage_type="qcow2",
        priority="default",
        retry: int = 0,
    ):
        """
        Create a new storage.

        :param user_id: User ID of the user executing the task and owner of the new storage.
        :type user_id: str
        :param pool_usage: Pool usage
        :type pool_usage: str
        :param parent_id: Parent storage ID
        :type parent_id: str
        :param size: Size like qemu-img command
        :type size: str
        :param storage_type: Storage type. Supported formats: qcow2, vmdk
        :type storage_type: str
        :param priority: Priority
        :type priority: str
        :return: Tuple with the new storage and the task ID
        :rtype: Tuple[isardvdi_common.models.storage.Storage, str]
        """
        # No parent_id means a brand-new blank disk; the storage worker's
        # create task omits the backing file in that case.
        parent_args = {}
        if parent_id:
            if not Storage.exists(parent_id):
                raise Exception(
                    "not_found",
                    f"Parent storage {parent_id} not found",
                )
            storage_parent = Storage(parent_id)
            if storage_parent.status != "ready":
                raise Exception(
                    "precondition_required",
                    "Parent storage is not ready",
                    "storage_not_ready",
                )
            if storage_parent.type != storage_type:
                raise Exception(
                    "precondition_required",
                    "Parent storage type does not match",
                )
            parent_args = {
                "parent_path": storage_parent.path,
                "parent_type": storage_parent.type,
            }

        storage = Storage.new_dict(
            user_id=user_id,
            pool_usage=pool_usage,
            parent_id=parent_id or None,
            format=storage_type,
        )
        storage.status_logs = [{"time": int(time()), "status": "created"}]

        storage.set_maintenance("create")
        storage.create_task(
            user_id=storage.user_id,
            queue=f"storage.{storage.pool.id}.{priority}",
            task="create",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "storage_path": storage.path,
                    "storage_type": storage.type,
                    "size": size,
                    **parent_args,
                },
            },
            dependents=[
                {
                    "queue": f"storage.{storage.pool.id}.{priority}",
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": storage.id,
                            "storage_path": storage.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                        }
                    ],
                },
            ],
        )

        return (storage, storage.task)

    @classmethod
    def create_new_storage_for_domain(
        cls,
        domain_id,
        user_id,
        pool_usage,
        parent_id=None,
        size=None,
        storage_type="qcow2",
        priority="default",
        retry: int = 0,
    ):
        """
        Create a new storage owned by a domain and enqueue the full RQ chain
        in one shot. For callers that need to inject the storage's id/path
        into the domain row *before* inserting the domain (so engine restart
        cleanup can trace the in-flight task via the ``storage_ids`` index),
        call ``Storage.new_dict`` + ``enqueue_disk_creation_chain_for_domain``
        directly instead of this convenience wrapper.

        :return: Tuple with the new storage and the root task ID
        :rtype: Tuple[isardvdi_common.models.storage.Storage, str]
        """
        storage = Storage.new_dict(
            user_id=user_id,
            pool_usage=pool_usage,
            parent_id=parent_id,
            format=storage_type,
        )
        storage.status_logs = [{"time": int(time()), "status": "created"}]
        storage.enqueue_disk_creation_chain_for_domain(
            domain_id=domain_id,
            size=size,
            priority=priority,
            retry=retry,
        )
        return (storage, storage.task)

    def enqueue_disk_creation_chain_for_domain(
        self,
        domain_id,
        size=None,
        priority="default",
        retry: int = 0,
    ):
        """
        Enqueue the chain that builds the qcow2 file on a storage worker and
        wires the resulting storage back into the domain row via the
        change-handler ``task_results.domain.handle_domain_change_storage``
        handler. The storage row must already exist (``Storage.new_dict``).

        Chain:
            create  (storage.{pool}.{priority} — root)
              -> qemu_img_info_backing_chain
                -> storage_update
                  -> domain_change_storage
                    -> update_status  (FAILED/CANCELED -> "Failed")

        The pre-MR-3 root ``domain_creating_disk`` is now applied
        inline (just a Creating/CreatingDiskFromScratch -> CreatingDisk
        status flip) because the post-MR-3 stack has no worker on the
        ``core`` queue — change-handler's stream consumer can only be
        driven by ``kind=result`` events from the storage worker.

        Pass ``size`` as a qemu-img size string for scratch disks (no
        parent). For template-derived disks the backing file determines
        sizing and ``size`` can be left as ``None``.

        :return: Root task ID
        :rtype: str
        """
        # Typed ``Error`` so apiv4's exception mapper produces 404/428
        # responses with a readable description, instead of a generic
        # 500 from a plain ``Exception``. Import inside the function to
        # avoid the snapshot-bind race documented in
        # ``reference_apiv4_error_factory_race.md``.
        from isardvdi_common.helpers.error_factory import Error

        if self.parent:
            if not Storage.exists(self.parent):
                raise Error(
                    "not_found",
                    f"Parent storage {self.parent} not found",
                    description_code="parent_storage_not_found",
                )
            storage_parent = Storage(self.parent)
            if storage_parent.status != "ready":
                raise Error(
                    "precondition_required",
                    f"Parent storage {self.parent} is not ready "
                    f"(status={storage_parent.status!r})",
                    description_code="storage_not_ready",
                )
            if storage_parent.type != self.type:
                raise Error(
                    "precondition_required",
                    f"Parent storage {self.parent} type ({storage_parent.type!r}) "
                    f"does not match this storage type ({self.type!r})",
                    description_code="parent_storage_type_mismatch",
                )
            parent_args = {
                "parent_path": storage_parent.path,
                "parent_type": storage_parent.type,
            }
        else:
            if not size:
                raise Error(
                    "bad_request",
                    "Scratch disk creation requires a size",
                    description_code="scratch_size_required",
                )
            parent_args = {}

        create_kwargs = {
            "storage_path": self.path,
            "storage_type": self.type,
            **parent_args,
        }
        if size is not None:
            create_kwargs["size"] = size

        # ``domain_creating_disk`` used to be the chain root on the
        # ``core`` queue, but post-MR-3 there is no worker that pops
        # ``core`` — the change-handler stream consumer only fires on
        # ``kind=result`` events from the storage worker, so a core
        # root deadlocks immediately. Apply the same status flip
        # inline (mirrors
        # ``change_handler.task_results.domain.handle_domain_creating_disk``
        # exactly) and root the chain on the first storage task.
        from isardvdi_common.models.domain import Domain

        if Domain.exists(domain_id):
            _d = Domain(domain_id)
            if _d.status in ("Creating", "CreatingDiskFromScratch"):
                _d.status = "CreatingDisk"

        self.set_maintenance("create")
        self.create_task(
            user_id=self.user_id,
            queue=f"storage.{self.pool.id}.{priority}",
            task="create",
            retry=retry,
            retry_intervals=15,
            job_kwargs={"kwargs": create_kwargs},
            dependents=[
                {
                    "queue": f"storage.{self.pool.id}.{priority}",
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "domain_change_storage",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "domain_id": domain_id,
                                            "storage_id": self.id,
                                        },
                                    },
                                    "dependents": [
                                        {
                                            "queue": "core",
                                            "task": "update_status",
                                            "job_kwargs": {
                                                "kwargs": {
                                                    "statuses": {
                                                        JobStatus.FAILED: {
                                                            "Failed": {
                                                                "domain": [domain_id],
                                                                "storage": [self.id],
                                                            },
                                                        },
                                                        JobStatus.CANCELED: {
                                                            "Failed": {
                                                                "domain": [domain_id],
                                                                "storage": [self.id],
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def enqueue_template_creation_chain_from_desktop(
        self,
        desktop_id,
        template_id,
        template_storage_id,
        priority="template",
        retry: int = 0,
        timeout=43200,
    ):
        """Enqueue the chain that turns this desktop's qcow2 into a template
        base disk plus a fresh overlay at the desktop's old path.

        Replaces the engine's deleted SSH path
        (``ui_actions.create_template_disks_from_domain`` +
        ``threads.launch_action_create_template_disk``) with an RQ task
        chain that mirrors the topology of
        :meth:`enqueue_disk_creation_chain_for_domain`.

        Caller invariants (apiv4 ``CommonTemplates.new_template``):
          * ``self`` is the desktop's existing Storage row,
            ``status == "ready"``.
          * ``template_storage_id`` already exists with
            ``status == "non_existing"``, allocated under the template pool,
            with ``parent = self.parent`` (so it inherits the desktop's
            backing chain root).
          * Both the desktop and template ``domains`` rows exist with
            ``status == "CreatingTemplate"``. The desktop is *not*
            ``Stopped`` — that prevents any other caller from acquiring
            either storage row via :meth:`set_maintenance` while the chain
            runs, so we deliberately do NOT call ``set_maintenance`` on
            ``self``.

        Chain (``move`` runs on the destination pool — that worker writes
        the new template file; the source-side backing-chain refresh runs
        on the source pool because that worker can read the desktop's
        rewritten overlay):

            storage.{dst_pool}.{prio}: move(method="auto",
                                            origin=desktop.path,
                                            destination=template.path,
                                            remove_source_file=True)
              -> storage.{dst_pool}.{prio}: create(storage_path=desktop.path,
                                                    storage_type=qcow2,
                                                    parent_path=template.path,
                                                    parent_type=qcow2)
                -> storage.{dst_pool}.{prio}: qemu_img_info_backing_chain(template)
                  -> core: storage_update           # template -> ready,
                                                    # _promote_domains_to_stopped
                    -> storage.{src_pool}.{prio}: qemu_img_info_backing_chain(desktop)
                      -> core: storage_update       # desktop -> ready,
                                                    # parent flipped to template
                        -> core: update_status      # FAILED/CANCELED -> Failed
                                                    # for both rows + both domains

        Status transitions:
            queued       → CreatingTemplate (set by caller before insert)
            running      → CreatingTemplate (no flip needed; rsync progress
                                              streams via stream:task-results
                                              → change-handler emit_task_feedback)
            finished     → Stopped          (via storage_update →
                                              _promote_domains_to_stopped on
                                              both storages)
            failed/canceled → Failed        (dependent update_status)

        Cancellation rides ``Task(self.task).cancel()``; ``run_with_progress``
        in the ``move`` task body listens via :class:`TaskCancelWatcher`
        and SIGTERMs rsync mid-run. The terminal ``update_status`` maps
        both ``FAILED`` and ``CANCELED`` to ``Failed`` on both rows.

        :param desktop_id: Source desktop domain id.
        :param template_id: New template domain id (already inserted).
        :param template_storage_id: New template storage id (already
            allocated via ``Storage.new_dict``).
        :param priority: RQ priority bucket. Defaults to ``"template"`` so the
            whole chain rides the dedicated governed template lane — a heavy
            whole-disk copy that must never block (or be blocked by) quick bulk
            creates, and never touches the reserved/std foreground pools.
        :param retry: Number of retries on the root ``move`` task.
        :param timeout: Per-task timeout in seconds (default 12 h, matches
            :meth:`rsync`).
        :return: Root task id.
        """
        # Typed ``Error`` so apiv4 maps to 404/428 instead of falling
        # through to 500. See the note in
        # ``enqueue_disk_creation_chain_for_domain`` for the in-function
        # import rationale.
        from isardvdi_common.helpers.error_factory import Error

        if not Storage.exists(template_storage_id):
            raise Error(
                "not_found",
                f"Template storage {template_storage_id} not found",
                description_code="template_storage_not_found",
            )
        template_storage = Storage(template_storage_id)
        dst_pool = template_storage.pool
        src_pool = self.pool
        if dst_pool is None or src_pool is None:
            raise Error(
                "precondition_required",
                f"No storage pool resolved for template {template_storage_id} "
                f"or desktop {desktop_id}",
                description_code="storage_no_pool",
            )

        # The new template storage is fresh (status="non_existing"); the
        # "create" maintenance label is allowlisted for that and skips the
        # domain-stopped check (the template domain is in CreatingTemplate
        # by construction). The desktop's existing storage is left in
        # "ready" — see docstring for the locking argument.
        template_storage.set_maintenance("create")

        self.create_task(
            user_id=self.user_id,
            queue=f"storage.{dst_pool.id}.{priority}",
            task="move",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "origin_path": self.path,
                    "destination_path": template_storage.path,
                    "method": "auto",
                    "remove_source_file": True,
                    # Surface rsync progress on the new template's row so
                    # the templates list in old-frontend / Vue 3 can render
                    # the same kind of progress bar Media downloads have.
                    "progress_domain_id": template_id,
                },
                "timeout": timeout,
            },
            dependents=[
                {
                    "queue": f"storage.{dst_pool.id}.{priority}",
                    "task": "create",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_path": self.path,
                            "storage_type": self.type,
                            "parent_path": template_storage.path,
                            "parent_type": template_storage.type,
                        }
                    },
                    "dependents": [
                        {
                            "queue": f"storage.{dst_pool.id}.{priority}",
                            "task": "qemu_img_info_backing_chain",
                            "job_kwargs": {
                                "kwargs": {
                                    "storage_id": template_storage_id,
                                    "storage_path": template_storage.path,
                                }
                            },
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_update",
                                    "dependents": [
                                        # Mirror main's post-SSH
                                        # ``Storage(template_storage_id).find()``:
                                        # re-resolve template_storage.parent
                                        # from on-disk backing-filename via
                                        # storage_update_parent. Without
                                        # this, the new template row stays
                                        # with parent=None even when the
                                        # disk has a real backing file.
                                        {
                                            "queue": "core",
                                            "task": "storage_update_parent",
                                            "job_kwargs": {
                                                "kwargs": {
                                                    "storage_id": template_storage_id,
                                                }
                                            },
                                        },
                                        {
                                            "queue": f"storage.{src_pool.id}.{priority}",
                                            "task": "qemu_img_info_backing_chain",
                                            "job_kwargs": {
                                                "kwargs": {
                                                    "storage_id": self.id,
                                                    "storage_path": self.path,
                                                }
                                            },
                                            "dependents": [
                                                {
                                                    "queue": "core",
                                                    "task": "storage_update",
                                                    "dependents": [
                                                        # Mirror main's
                                                        # post-SSH
                                                        # ``Storage(domain_storage_id).find()``:
                                                        # flip the desktop
                                                        # storage's parent
                                                        # to the new
                                                        # template via
                                                        # storage_update_parent.
                                                        {
                                                            "queue": "core",
                                                            "task": "storage_update_parent",
                                                            "job_kwargs": {
                                                                "kwargs": {
                                                                    "storage_id": self.id,
                                                                }
                                                            },
                                                        },
                                                        {
                                                            "queue": "core",
                                                            "task": "update_status",
                                                            "job_kwargs": {
                                                                "kwargs": {
                                                                    "statuses": {
                                                                        JobStatus.FAILED: {
                                                                            "Failed": {
                                                                                "domain": [
                                                                                    desktop_id,
                                                                                    template_id,
                                                                                ],
                                                                                "storage": [
                                                                                    self.id,
                                                                                    template_storage_id,
                                                                                ],
                                                                            },
                                                                        },
                                                                        JobStatus.CANCELED: {
                                                                            "Failed": {
                                                                                "domain": [
                                                                                    desktop_id,
                                                                                    template_id,
                                                                                ],
                                                                                "storage": [
                                                                                    self.id,
                                                                                    template_storage_id,
                                                                                ],
                                                                            },
                                                                        },
                                                                    },
                                                                },
                                                            },
                                                        },
                                                    ],
                                                }
                                            ],
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def enqueue_registry_download_chain_for_domain(
        self,
        domain_id,
        url,
        headers=None,
        insecure_ssl=False,
        google_drive_cookie=None,
        priority="low",
        retry: int = 0,
    ):
        """Enqueue the chain that downloads a registry-domain qcow2.

        Replaces the engine's deleted ``DownloadThread.table=='domains'``
        SSH-curl path with the same RQ-task topology already used by
        media URL downloads. Status transitions:

            queued       → DownloadStarting (set by caller before insert)
            running      → Downloading      (flipped inside download_url_for_domain)
            finished     → Stopped          (via storage_update →
                                              _promote_domains_to_stopped)
            failed/canceled → Failed        (dependent update_status)

        Cancellation rides ``Task(self.task).cancel()``; the
        ``download_url_for_domain`` body's :class:`TaskCancelWatcher`
        notices via the generic ``task:cancel:<id>`` pub/sub channel.

        :return: Root task id.
        """
        pool = self.pool
        if pool is None:
            raise Exception(
                "precondition_required",
                f"No storage pool found for domain {domain_id}",
            )

        download_kwargs = {
            "domain_id": domain_id,
            "storage_id": self.id,
            "url": url,
            "dest_path": self.path,
            "headers": list(headers or []),
            "insecure_ssl": bool(insecure_ssl),
            "google_drive_cookie": google_drive_cookie,
        }

        self.set_maintenance("download")
        self.create_task(
            user_id=self.user_id,
            queue=f"storage.{pool.id}.{priority}",
            task="download_url_for_domain",
            retry=retry,
            retry_intervals=15,
            job_kwargs={"kwargs": download_kwargs},
            dependents=[
                {
                    "queue": f"storage.{pool.id}.{priority}",
                    "task": "qemu_img_info_backing_chain",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update",
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "update_status",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "statuses": {
                                                JobStatus.FAILED: {
                                                    "Failed": {
                                                        "domain": [domain_id],
                                                        "storage": [self.id],
                                                    }
                                                },
                                                JobStatus.CANCELED: {
                                                    "Failed": {
                                                        "domain": [domain_id],
                                                        "storage": [self.id],
                                                    }
                                                },
                                            },
                                        },
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def abort_operations(
        self,
        user_id,
    ):
        """
        Create a task to abort the current storage operations.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :return: Task ID
        :rtype: str
        """
        storage_pool = StoragePool.get_best_for_action(
            "abort", path=self.directory_path
        )

        # The old ``delete_task`` chain root on ``core`` deadlocks
        # post-MR-3 (no worker on ``core`` — change-handler's stream
        # consumer can only be driven by ``kind=result`` events from a
        # storage worker). Cancel the in-flight RQ Task in-process,
        # then root the chain on the storage-side
        # ``qemu_img_info_backing_chain`` so the consumer takes over
        # naturally.
        if self.task and Task.exists(self.task):
            try:
                Task(self.task).cancel()
            except Exception:
                # Best-effort — Task.cancel is itself best-effort
                # (see Task.cancel docstring). Even if cancel raises,
                # the post-abort qemu_img_info_backing_chain + storage_update
                # below will reset the storage row to its real on-disk
                # state.
                pass

        self.create_task(
            user_id=user_id,
            queue=f"storage.{storage_pool.id}.default",
            task="qemu_img_info_backing_chain",
            blocking=False,
            job_kwargs={
                "kwargs": {
                    "storage_id": self.id,
                    "storage_path": self.path,
                }
            },
            dependents=[
                {
                    "queue": "core",
                    "task": "storage_update",
                }
            ],
        )

        return self.task

    """
    Tasks for storages with uuid
    """

    def set_path(
        self,
        user_id,
        new_path,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to set the storage path to a new path.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param new_path: New path
        :type new_path: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        if get_storage_id_from_path(new_path) != self.id:
            raise Exception(
                "precondition_required",
                f"Storage ID {self.id} does not match the path {new_path}",
                "storage_id_mismatch",
            )

        if self.path == new_path:
            raise Exception(
                "bad_request",
                f"Path {new_path} is the same as the storage path",
            )

        # ``storage_update_dict`` was the chain root on ``core``, but
        # post-MR-3 the ``core`` queue has no worker. Apply the storage
        # row update inline (mirrors
        # ``change_handler.task_results.storage.handle_storage_update_dict``:
        # set status, directory_path, qemu-img-info.filename) and root
        # the chain on the first storage task (``touch``).
        from rethinkdb import r as _r

        with self._rdb_context():
            _r.table("storage").get(self.id).update(
                {
                    "status": "ready",
                    "directory_path": new_path.split("/" + self.id)[0],
                    "qemu-img-info": {"filename": new_path},
                }
            ).run(self._rdb_connection)

        self.set_maintenance("set_path")
        self.create_task(
            blocking=True,
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('touch', path=new_path).id}.{priority}",
            task="touch",
            retry=retry,
            retry_intervals=15,
            job_kwargs={"kwargs": {"path": new_path}},
            dependents=[
                {
                    "queue": f"storage.{StoragePool.get_best_for_action('find', path=self.directory_path).id}.{priority}",
                    "task": "find",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update_pool",
                            "job_kwargs": {
                                "kwargs": {
                                    "storage_id": self.id,
                                }
                            },
                            "dependents": [
                                {
                                    "queue": "core",
                                    "task": "storage_update_parent",
                                    "job_kwargs": {"kwargs": {"storage_id": self.id}},
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def delete_path(
        self,
        user_id,
        path,
        priority="default",
        retry: int = 0,
    ):
        """
        Create a task to delete the disk image from the provided path.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param path: Path to delete
        :type path: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        if get_storage_id_from_path(path) != self.id:
            raise Exception(
                "precondition_required",
                f"Storage ID {self.id} does not match the path {path}",
                "storage_id_mismatch",
            )

        if self.path == path:
            raise Exception(
                "bad_request",
                f"Path {path} is the same as the storage path",
            )

        self.set_maintenance("delete_path")
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('delete', path=self.directory_path).id}.{priority}",
            task="delete",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "path": path,
                },
            },
            dependents=[
                {
                    "queue": f"storage.{StoragePool.get_best_for_action('find', path=self.directory_path).id}.{priority}",
                    "task": "find",
                    "job_kwargs": {
                        "kwargs": {
                            "storage_id": self.id,
                            "storage_path": self.path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update_pool",
                            "job_kwargs": {
                                "kwargs": {
                                    "storage_id": self.id,
                                }
                            },
                        }
                    ],
                },
            ],
        )

        return self.task
