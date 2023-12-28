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
