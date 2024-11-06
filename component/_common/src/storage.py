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

from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.user import User
from rq.job import JobStatus

from . import domain
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
        return f"{storage_pool.mountpoint}/{self.category}/{storage_pool.get_usage_path(self.pool_usage)}/{self.id}.{self.type}"

    @property
    def children(self):
        """
        Returns the storages that have this storage as parent.
        """
        return self.get_index([self.id], index="parent")

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
                                    }
                                }
                            },
                        }
                    ],
                }
            ],
        )
        return self.task

    def set_maintenance(self, action):
        """
        Set storage and it's domains to maintenance status.

        :param storage: Storage object
        :type storage: isardvdi_common.storage.Storage
        :param action: Action
        :type action: str
        """
        for domain in self.domains:
            if domain.status not in ["Stopped", "Failed"]:
                raise Exception(
                    {
                        "error": "precondition_required",
                        "description": f"Domain {domain.id} must be Stopped in order to operate with its' storage. It's actual status is {domain.status}",
                        "description_code": "desktops_not_stopped",
                    }
                )
        for domain in self.domains:
            domain.status = "Maintenance"
            domain.current_action = action
        self.status = "maintenance"

    def rsync(
        self,
        user_id,
        destination_path,
        bwlimit=0,
        remove_source_file=True,
        priority="default",
    ):
        """
        Create a task to move the storage.

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
        :return: Task ID
        :rtype: str
        """
        origin_path = self.path
        if self.path == destination_path:
            raise Exception(
                {
                    "error": "precondition_required",
                    "description": "The origin and destination paths must be different",
                    "description_code": "origin_destination_paths_must_be_different",
                }
            )
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
                }
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
