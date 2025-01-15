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

from uuid import uuid4

from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.user import User
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


def new_storage_dict(user_id, pool_usage, parent_id=None, format="qcow2"):
    """
    Create a new storage dictionary.

    :param user_id: User ID
    :type user_id: str
    :param pool_usage: Storage pool_usage: desktop or template
    :type pool_usage: str
    :param parent_id: Parent ID
    :type parent_id: str
    """

    return {
        "id": str(uuid4()),
        "type": format,
        "directory_path": new_storage_directory_path(user_id, pool_usage),
        "parent": parent_id,
        "user_id": user_id,
        "status": "created",
        "perms": ["r", "w"] if pool_usage == "desktop" else ["r"],
        "status_logs": [],
    }


class Storage(RethinkCustomBase):
    """
    Manage Storage Objects

    Use constructor with keyword arguments to create new Storage Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Storage Object.
    """

    _rdb_table = "storage"

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

    def check_backing_chain(self, user_id, blocking=True):
        """
        Create a task to check the storage.

        :param user_id: User ID
        :type user_id: str
        :return: Task ID
        :rtype: str
        """

        self.create_task(
            blocking=blocking,
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=self.directory_path).id}.default",
            task="qemu_img_info_backing_chain",
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
                {
                    "error": "precondition_required",
                    "description": f"Storage {self.id} must be Ready in order to operate with it. It's actual status is {self.status}",
                    "description_code": "storage_not_ready",
                }
            )
        domains = self.domains
        if any(domain.status != "Stopped" for domain in domains):
            raise Exception(
                {
                    "error": "precondition_required",
                    "description": f"Storage {self.id} must have all domains stopped in order to set it to maintenance. Some desktops are not stopped.",
                    "description_code": "desktops_not_stopped",
                }
            )
        if any(domain.kind != "desktop" for domain in domains):
            if len(self.children) > 0:
                raise Exception(
                    {
                        "error": "precondition_required",
                        "description": f"Storage {self.id} has children storages. It must be empty in order to set it to maintenance.",
                        "description_code": "storage_has_children",
                    }
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
                {
                    "error": "precondition_required",
                    "description": f"Storage {self.id} must be maintenance in order to return back to ready status. It's actual status is {self.status}",
                    "description_code": "storage_not_maintenance",
                }
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
        timeout=1200,  # Default redis timeout is 180 (3 minutes)
    ):
        """
        Create a task to move the storage using rsync.

        :param user_id: User ID
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
        queue_origin = f"storage.{StoragePool.get_best_for_action('check_existence', path=self.directory_path).id}.{priority}"
        self.set_maintenance("move")
        self.create_task(
            blocking=True,
            user_id=user_id,
            queue=queue_rsync,
            task="move",
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
        destination_path,
        priority="default",
    ):
        """
        Create a task to move the storage using mv.

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
            user_id=self.user_id,
            queue=queue_mv,
            task="move",
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

    def delete(
        self,
        user_id,
        priority="default",
    ):
        """
        Create a task to delete the storage.

        :param user_id: User ID of the user executing the task
        :type user_id: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        :rtype: str
        """
        self.set_maintenance("delete")
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('delete', path=self.directory_path).id}.{priority}",
            task="delete",
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
                                },
                                "finished": {
                                    "deleted": {
                                        "storage": [self.id],
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

    def check_existence(
        self,
        user_id,
    ):
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('check_existence', path=self.directory_path).id}.default",
            task="check_existence",
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

    def qemu_img_info(
        self,
        user_id,
    ):
        """
        Create a task to update the storage qemu-img info.

        :param user_id: User ID
        :type user_id: str
        :return: Task ID
        :rtype: str
        """
        self.create_task(
            user_id=user_id,
            queue=f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=self.directory_path).id}.default",
            task="qemu_img_info",
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

    def update_parent(
        self,
        user_id,
    ):
        """
        Create a task to update the parent of the storage.

        :param user_id: User ID
        :type user_id: str
        :return: Task ID
        :rtype: str
        """
        self.create_task(
            user_id=user_id,
            queue="core",
            task="storage_update_parent",
            job_kwargs={
                "kwargs": {
                    "storage_id": self.id,
                }
            },
            dependencies=[
                {
                    "queue": "core",
                    "task": "storage_update",
                    "dependencies": [
                        {
                            "queue": f"storage.{StoragePool.get_best_for_action('check_backing_filename', path=self.directory_path).id}.default",
                            "task": "check_backing_filename",
                            "dependencies": [
                                {
                                    "queue": f"storage.{StoragePool.get_best_for_action('qemu_img_info', path=self.directory_path).id}.default",
                                    "task": "qemu_img_info",
                                    "job_kwargs": {
                                        "kwargs": {
                                            "storage_id": self.id,
                                            "storage_path": self.path,
                                        }
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        return self.task

    def increase_size(
        self,
        increment,
        priority="default",
    ):
        """
        Create a task to increase the storage size.

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
            user_id=self.user_id,
            queue=resize_queue,
            task="resize",
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
                        },
                        {
                            "queue": "core",
                            "task": "storage_domains_force_update",
                            "job_kwargs": {"kwargs": {"storage_id": self.id}},
                        },
                    ],
                }
            ],
        )

        return self.task

    def virt_win_reg(
        self,
        registry_patch,
        priority="default",
    ):
        """
        Create a task to write a windows registry patch to the storage.
        This task will only work with storages that have Windows XP or newer installed.
        https://libguestfs.org/virt-win-reg.1.html

        :param registry_patch: Windows registry patch
        :type registry_patch: str
        :param priority: Priority
        :type priority: str
        :return: Task ID
        """
        queue_virt_win_reg = f"storage.{StoragePool.get_best_for_action('virt_win_reg', path=self.directory_path).id}.{priority}"

        self.set_maintenance("virt_win_reg")
        self.create_task(
            user_id=self.user_id,
            queue=queue_virt_win_reg,
            task="virt_win_reg",
            job_kwargs={
                "kwargs": {
                    "storage_path": self.path,
                    "registry_patch": registry_patch,
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

    def abort_operations(
        self,
        user_id,
    ):
        """
        Create a task to abort the current storage operations.

        :param user_id: User ID
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
