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

from os import remove
from subprocess import PIPE, Popen
from time import sleep

from isardvdi_protobuf.queue.storage.v1 import ConvertRequest, DiskFormat
from rq import Queue, get_current_job


def convert(convert_request):
    """
    Convert disk.

    :param convert_request: Protobuf Message
    :type convert_request: isardvdi_protobuf.queue.storage.v1.ConvertRequest
    :return: Exit code of qemu-img command
    :rtype: int
    """
    job = get_current_job()
    if (
        convert_request.compression
        # https://github.com/danielgtaylor/python-betterproto/issues/174
        and convert_request.format == DiskFormat.DISK_FORMAT_QCOW2
    ):
        compress = ["-c"]
    else:
        compress = []
    # https://github.com/danielgtaylor/python-betterproto/issues/174
    if convert_request.format == DiskFormat.DISK_FORMAT_UNSPECIFIED:
        raise ValueError("Please specify a disk format")
    if convert_request.format > 2:
        raise ValueError("Format convert_request.format not supported")
    with Popen(
        [
            "qemu-img",
            "convert",
            "-p",
            *compress,
            "-O",
            # https://github.com/danielgtaylor/python-betterproto/issues/174
            DiskFormat(convert_request.format).name.rsplit("_")[-1].lower(),
            convert_request.source_disk_path,
            convert_request.dest_disk_path,
        ],
        stdout=PIPE,
    ) as process:
        while process.poll() is None:
            job.meta["progress"] = (
                float(process.stdout.read1().decode().split("(", 1)[1].split("/", 1)[0])
                / 100
            )
            job.save_meta()
            Queue("core", connection=job.connection).enqueue(
                "task.feedback", task_id=job.id, result_ttl=0
            )
            sleep(5)
            process.stdout.read1()
        if process.returncode == 0:
            job.meta["progress"] = 1
            job.save_meta()
        return process.returncode


def delete(path):
    """
    Delete disk.

    :param path: Path to disk
    :type path: str
    """
    remove(path)
