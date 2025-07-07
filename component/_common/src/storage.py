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
from uuid import uuid4

from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.user import User
from rethinkdb import r
from rq.job import JobStatus

from . import domain
from .default_storage_pool import DEFAULT_STORAGE_POOL_ID
from .rethink_custom_base_factory import RethinkCustomBase
from .task import Task


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
    if User.exists(user_id):
        return f"{storage_pool.mountpoint}/{User(user_id).category}/{storage_pool.get_usage_path(pool_usage)}"


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

        return Storage(**storage_dict)

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
        return StoragePool.get_by_path(self.directory_path)[0]

    @property
    def pool_usage(self):
        """
        Returns the storage pool usage of storage.
        """
        return self.pool.get_usage_by_path(self.directory_path)

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
        return f"{storage_pool.mountpoint}/{self.category}/{storage_pool.get_usage_path(self.pool_usage)}/{self.id}.{self.type}"

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

        if self.pool.get_usage_by_path(self.path) == usage:
            return self.directory_path

        return new_storage_directory_path(self.user_id, usage)

    def set_storage_pool(self, storage_pool):
        """
        Change storage pool.

        :param storage_pool: Storage Pool object
        :type storage_pool: isardvdi_common.storage_pool.StoragePool
        """
        if self.pool == storage_pool:
            return
        if self.pool_usage is None:
            return None

        if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
            self.directory_path = f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(self.pool_usage)}"
        else:
            self.directory_path = f"{storage_pool.mountpoint}/{self.category}/{storage_pool.get_usage_path(self.pool_usage)}"

    def get_storage_pool_path(self, storage_pool):
        """
        Get storage in pool.

        :param storage_pool: Storage Pool object
        :type storage_pool: isardvdi_common.storage_pool.StoragePool
        """
        if self.pool_usage is None:
            return None

        if storage_pool.id == DEFAULT_STORAGE_POOL_ID:
            return f"{storage_pool.mountpoint}/{storage_pool.get_usage_path(self.pool_usage)}"
        else:
            return f"{storage_pool.mountpoint}/{self.category}/{storage_pool.get_usage_path(self.pool_usage)}"

    @property
    def children(self):
        """
        Returns the storages that have this storage as parent.
        """
        return self.get_index([self.id], index="parent")

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
        """
        if self.parent is None:
            return []
        return [Storage(self.parent)] + Storage(self.parent).parents

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
        """
        Returns the category of the storage user_id owner
        """
        if User.exists(self.user_id):
            return User(self.user_id).category
        return None

    @classmethod
    def create_from_path(cls, path):
        """
        Create Storage from path.

        :param path: Path of storage
        :type path: str
        :return: Storage object
        :rtype: isardvdi_common.storage.Storage
        """
        return Storage(
            id=get_storage_id_from_path(path),
            type=path.rsplit(".", 1)[-1],
            directory_path=path.rsplit("/", 1)[0],
            status="ready",
        )

    @classmethod
    def get_by_path(cls, path):
        """
        Get storage by path.

        :param path: Path of storage
        :type path: str
        :return: Storage object
        :rtype: isardvdi_common.storage.Storage
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
            raise Exception(
                "precondition_required",
                f"Storage {self.id} have the pending task {self.task}",
            )
        self.task = Task(*args, **kwargs).id

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
                            "task": "storage_domains_force_update",
                            "job_kwargs": {"kwargs": {"storage_id": self.id}},
                        }
                    ],
                }
            ],
        )
        return self.task

    def check_backing_chain(self, user_id, blocking=True, retry=3):
        """
        Create a task to check the storage.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :return: Task ID
        :rtype: str
        """

        self.create_task(
            blocking=blocking,
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info_backing_chain', path=self.directory_path).id}.default",
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
        :type storage: isardvdi_common.storage.Storage
        :param action: Action
        :type action: str
        """
        if self.status != "ready":
            raise Exception(
                "precondition_required",
                f"Storage {self.id} must be Ready in order to operate with it. It's actual status is {self.status}",
                "storage_not_ready",
            )
        domains = self.domains
        if any(domain.status != "Stopped" for domain in domains):
            raise Exception(
                "precondition_required",
                f"Storage {self.id} must have all domains stopped in order to set it to maintenance. Some desktops are not stopped.",
                "desktops_not_stopped",
            )
        if any(domain.kind != "desktop" for domain in domains):
            if len(self.children) > 0:
                raise Exception(
                    "precondition_required",
                    f"Storage {self.id} has children storages. It must be empty in order to set it to maintenance.",
                    "storage_has_children",
                )
        for domain in self.domains:
            domain.status = "Maintenance"
            domain.current_action = action
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
                                "status": "ready",
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
                                                self.status: {
                                                    "storage": [self.id],
                                                },
                                            },
                                            JobStatus.FAILED: {
                                                self.status: {
                                                    "storage": [self.id],
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                            {
                                "queue": "core",
                                "task": "storage_domains_force_update",
                                "job_kwargs": {"kwargs": {"storage_id": self.id}},
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
                        {
                            "queue": "core",
                            "task": "storage_domains_force_update",
                            "job_kwargs": {"kwargs": {"storage_id": self.id}},
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
                    "dependents": {
                        "queue": "core",
                        "task": "storage_delete",
                        "job_kwargs": {"kwargs": {"storage_id": self.id}},
                    },
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
        resize_queue = (
            f"storage.{StoragePool.get_best_for_action('resize').id}.{priority}"
        )

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
                    "queue": resize_queue,
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
        queue_backing_chain = f"storage.{StoragePool.get_best_for_action('qemu_img_info_backing_chain',path=self.directory_path).id}.{secondary_priority}"

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
        disconnect_queue = (
            f"storage.{StoragePool.get_best_for_action('disconnect').id}.{priority}"
        )

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

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param new_storage: New storage object
        :type new_storage: isardvdi_common.storage.Storage
        :param new_storage_type: New storage type. Supported formats: qcow2, vmdk
        :type new_storage_type: str
        :param new_storage_status: New storage status
        :type new_storage_status: str
        :param compress: Whether to compress the new storage or not
        :type compress: bool
        :param priority: Priority
        :type priority: str
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
                "timeout": 4096,
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

        new_storage = Storage().new_dict(
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
        :rtype: Tuple[isardvdi_common.storage.Storage, str]
        """
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

        storage = Storage().new_dict(
            user_id=user_id,
            pool_usage=pool_usage,
            parent_id=parent_id,
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
        storage_pool = StoragePool.get_best_for_action("abort")

        self.create_task(
            user_id=user_id,
            queue="core",
            task="delete_task",
            blocking=False,
            job_kwargs={
                "kwargs": {
                    "task_id": self.task,
                }
            },
            dependents=[
                {
                    "queue": f"storage.{storage_pool.id}.default",
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

        self.set_maintenance("set_path")
        self.create_task(
            blocking=True,
            user_id=user_id,
            queue="core",
            task="storage_update_dict",
            retry=retry,
            retry_intervals=15,
            job_kwargs={
                "kwargs": {
                    "id": self.id,
                    "status": "ready",
                    "directory_path": new_path.split("/" + self.id)[0],
                    "qemu-img-info": {
                        "filename": new_path,
                    },
                }
            },
            dependents=[
                {
                    "queue": f"storage.{StoragePool.get_best_for_action('touch').id}.{priority}",
                    "task": "touch",
                    "job_kwargs": {
                        "kwargs": {
                            "path": new_path,
                        }
                    },
                    "dependents": [
                        {
                            "queue": f"storage.{StoragePool.get_best_for_action('find').id}.{priority}",
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
                                            "task": "storage_domains_force_update",
                                            "job_kwargs": {
                                                "kwargs": {"storage_id": self.id}
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
            queue=f"storage.{StoragePool.get_best_for_action('delete').id}.{priority}",
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
                    "queue": f"storage.{StoragePool.get_best_for_action('find').id}.{priority}",
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
