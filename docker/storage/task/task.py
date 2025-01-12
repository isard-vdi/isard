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

import shutil
import tempfile
from json import loads
from os import environ, makedirs, remove, rename
from os.path import basename, dirname, isdir, isfile, join
from re import search
from subprocess import PIPE, CalledProcessError, Popen, check_output, run
from time import sleep

from isardvdi_common.task import Task
from isardvdi_protobuf_old.queue.storage.v1 import ConvertRequest, DiskFormat
from rq import Queue, get_current_job


def _same_file(file1, file2):
    """
    Check if two files are the same.
    Use filename, mtime and size to check if two files are the same.

    :param file1: Path to first file
    :type file1: str
    :param file2: Path to second file
    :type file2: str
    :return: True if files are the same, False otherwise
    :rtype: bool
    """

    if not isfile(file1) or not isfile(file2):
        return False

    return (
        basename(file1) == basename(file2)
        and isfile(file1)
        and isfile(file2)
        and (
            check_output(["stat", "-c", "%Y", file1]).decode()
            == check_output(["stat", "-c", "%Y", file2]).decode()
        )
        and (
            check_output(["stat", "-c", "%s", file1]).decode()
            == check_output(["stat", "-c", "%s", file2]).decode()
        )
    )


def extract_progress_from_qemu_img_convert_output(process):
    """
    Extract progress from qemu-img convert standard output

    :param process: Process executed
    :type process: Popen object
    :return: Progress percentage as decimal
    :rtype: float
    """
    return (
        float(process.stdout.read1().decode().split("(", 1)[1].split("/", 1)[0]) / 100
    )


def extract_progress_from_rsync_output(process):
    """
    Extract progress from rsync standard output.

    :param process: Process executed
    :type process: Popen object
    :return: Progress percentage as decimal
    :rtype: float
    """
    output = process.stdout.read1().decode()

    # Split by lines to handle multi-line output
    lines = output.splitlines()

    # Find the line with the progress information

    for line in lines:
        if "%" in line:  # Look for lines that contain a percentage
            try:
                # Split by space and look for the percentage part
                percentage_str = line.split()[
                    1
                ]  # This assumes the percentage is always the second item
                if percentage_str.endswith("%"):
                    percentage_str = percentage_str[:-1]  # Remove the '%'
                progress = float(percentage_str) / 100  # Convert to float and scale
                break  # Exit the loop once we find the percentage
            except (ValueError, IndexError) as e:
                print("Error parsing progress:", e)
                progress = 0.0  # Default value if parsing fails
        else:
            progress = 0.0  # Default if no progress line is found
    try:
        return progress
    except UnboundLocalError:
        raise ValueError("Source rsync file not found")


def run_with_progress(command, extract_progress):
    """
    Run command reporting progress to RQ job metadata.

    :param command: Array of command arguments to be executed
    :type command: List of str
    :param extract_progress: Function to extract progress from stdout of command executed
    :type extrct_progress: Callable function with progress as firt parameter
    :return: Exit code of command executed
    :rtype: int
    """
    job = get_current_job()
    with Popen(command, stdout=PIPE) as process:
        while process.poll() is None:
            job.meta["progress"] = round(extract_progress(process), 2)
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


def create(storage_path, storage_type, size=None, parent_path=None, parent_type=None):
    """
    Create disk.

    :param storage_path: Path of new disk
    :type storage_path: str
    :param storage_type: Format of new disk
    :type storage_type: str
    :param size: Size of new disk as qemu-img string format
    :type size: str
    :param parent_path: Path of backing file
    :type parent_path: str
    :param parent_type: Format of backing file
    :type parent_type: str
    :return: Exit code of qemu-img command
    :rtype: int
    """
    if not isdir(dirname(storage_path)):
        makedirs(dirname(storage_path), exist_ok=True)
    backing_file = []
    if parent_path and parent_type:
        backing_file = ["-b", parent_path, "-F", parent_type]
    if size:
        size = [size]
    else:
        size = []

    options = ""
    if storage_type == "qcow2":
        options = f"""cluster_size={
            environ.get('QCOW2_CLUSTER_SIZE','4k')
        },extended_l2={
            environ.get('QCOW2_EXTENDED_L2','off')
        }"""

    command = [
        "qemu-img",
        "create",
        "-f",
        storage_type,
        *backing_file,
        storage_path,
        *size,
    ]

    if options:
        command.insert(6, "-o")
        command.insert(7, options)
    return run(
        command,
        check=True,
    ).returncode


def qemu_img_info(storage_id, storage_path):
    """
    Get storage data with `qemu-img info` data updated.

    :param storage_id: Storage ID
    :type storage_id: str
    :param storage_path: Storage path
    :type storage_path: str
    :return: Storage data to update
    :rtype: dict
    """
    qemu_img_info_data = loads(
        check_output(
            [
                "qemu-img",
                "info",
                "-U",
                "--output",
                "json",
                storage_path,
            ],
        )
    )
    qemu_img_info_data.setdefault("backing-filename")
    qemu_img_info_data.setdefault("backing-filename-format")
    qemu_img_info_data.setdefault("full-backing-filename")
    return {"id": storage_id, "status": "ready", "qemu-img-info": qemu_img_info_data}


def qemu_img_info_backing_chain(storage_id, storage_path):
    """
    Get storage data with `qemu-img info` data updated.

    :param storage_id: Storage ID
    :type storage_id: str
    :param storage_path: Storage path
    :type storage_path: str
    :return: Storage data to update
    :rtype: dict
    """

    completed_process = run(
        [
            "qemu-img",
            "info",
            "-U",
            "--backing-chain",
            "--output",
            "json",
            storage_path,
        ],
        capture_output=True,
    )
    storage_data = {"id": storage_id}
    if completed_process.returncode == 0:
        storage_data["status"] = "ready"
        qemu_img_info_data = loads(completed_process.stdout)
        qemu_img_info_data[0].setdefault("backing-filename")
        qemu_img_info_data[0].setdefault("backing-filename-format")
        qemu_img_info_data[0].setdefault("full-backing-filename")
        storage_data["qemu-img-info"] = qemu_img_info_data[0]
    else:
        path = (
            search(
                rb"^qemu-img: Could not open \'([^\']*)\': ", completed_process.stderr
            )
            .group(1)
            .decode()
        )
        if path == storage_path:
            storage_data["status"] = "deleted"
        elif path == qemu_img_info(storage_id, storage_path).get(
            "qemu-img-info", {}
        ).get("backing-filename"):
            storage_data["status"] = "orphan"
        else:
            storage_data["status"] = "broken_chain"

    return storage_data


def check_existence(storage_id, storage_path):
    """
    Returns Storage data with `ready` status if file exists otherwise with `deleted` status.

    :param storage_path: Storage path
    :type storage_id: str
    :return: Storage data to update
    :rtype: dict
    """
    storage = {"id": storage_id}
    if isfile(storage_path):
        storage["status"] = "ready"
    else:
        storage["status"] = "deleted"
    return storage


def check_media_existence(media_id, path):
    """
    Returns Media data with `Downloaded` status if file exists otherwise with `deleted` status.

    :param storage_path: Media path
    :type storage_id: str
    :return: Media data to update
    :rtype: dict
    """
    media = {"id": media_id}
    if path and isfile(path):
        media["status"] = "Downloaded"
        media["total_percent"] = 100
    else:
        media["status"] = "deleted"
    return media


def check_backing_filename():
    """
    Check backing filename

    :return: List of Storage data to update
    :rtype: list
    """
    result = []
    task = Task(get_current_job().id)
    if task.depending_status == "finished":
        for dependency in task.dependencies:
            if dependency.task == "qemu_img_info":
                backing_filename = dependency.result.get("qemu-img-info", {}).get(
                    "full-backing-filename"
                )
                if backing_filename and not isfile(backing_filename):
                    dependency.result["status"] = "orphan"
                result.append(dependency.result)
    return result


def move(origin_path, destination_path, method, bwlimit=0, remove_source_file=True):
    """
    Move disk.

    :param origin_path: Path of the original file
    :type origin_path: str
    :param destination_path: Path of the destination file
    :type destination_path: str
    :param rsync: True to use rsync
    :type rsync: bool
    :return: Exit code of rsync command or 0 if rsync is False
    :rtype: int
    """
    if not isfile(origin_path):
        raise ValueError(f"Path {origin_path} not found")

    if isfile(destination_path) and _same_file(origin_path, destination_path):
        if remove_source_file:
            return remove(origin_path)
        return 0

    if not isdir(dirname(destination_path)):
        makedirs(dirname(destination_path), exist_ok=True)
    if method == "mv":
        shutil.move(origin_path, destination_path)
        return 0
    elif method == "rsync":
        return run_with_progress(
            [
                "rsync",
                "-a",
                "--info=progress,flist0",
                *(["--bwlimit=" + str(bwlimit)] if bwlimit else []),
                *(["--remove-source-files"] if remove_source_file else []),
                origin_path,
                destination_path,
            ],
            extract_progress_from_rsync_output,
        )
    else:
        raise ValueError(f"Invalid move method: {method}")


def move_delete(path):
    """
    Move the disk to a "deleted" subdirectory within the same directory path

    :param path: Path of the original file
    :type path: str
    :rtype: int
    """
    if isfile(path):
        delete_path = join(dirname(path), "deleted")
        if not isdir(delete_path):
            makedirs(delete_path, exist_ok=True)

        rename(path, join(delete_path, basename(path)))
        return 0
    else:
        raise ValueError(f"Path {path} not found")


def convert(convert_request):
    """
    Convert disk.

    :param convert_request: Protobuf Message
    :type convert_request: isardvdi_protobuf_old.queue.storage.v1.ConvertRequest
    :return: Exit code of qemu-img command
    :rtype: int
    """
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
    return run_with_progress(
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
        extract_progress_from_qemu_img_convert_output,
    )


def delete(path):
    """
    Delete disk.

    :param path: Path to disk
    :type path: str
    """
    if isfile(path):
        remove(path)


def virt_win_reg(storage_path, registry_patch):
    """
    Copy reg file to tmp
    Apply registry patch to qcow2 storage_id disk using virt-win-reg
    Remove reg file from tmp

    :param storage_id: Storage ID
    :type storage_id: str
    :param registry_patch: Registry patch
    :type registry_patch: str
    :return: Exit code of regedit command
    :rtype: int
    """
    try:
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(registry_patch.encode())
            fp.flush()
            result = run(
                [
                    "virt-win-reg",
                    "--merge",
                    storage_path,
                    fp.name,
                ],
                capture_output=True,  # Capture stdout and stderr
                text=True,  # Decode output as text
                check=True,  # Raise CalledProcessError on failure
            )
            return result.returncode
    except CalledProcessError as cpe:
        # Return error details, including captured stderr
        return (
            f"Error: Command failed with return code {cpe.returncode}. "
            f"stderr: {cpe.stderr.strip() or 'No error message provided.'}"
        )
    except Exception as e:
        # Handle other exceptions
        return f"Error: {str(e)}"


def resize(storage_path, increment):
    """
    Increase disk size

    :param storage_path: Path to disk
    :type storage_id: str
    :param increment: Size of the increment in GB
    :type increment: int
    :return: Exit code of qemu-img command
    :rtype: int
    """
    try:
        return run(
            [
                "qemu-img",
                "resize",
                storage_path,
                f"+{increment}G",
            ]
        ).returncode
    except Exception as e:
        return e
