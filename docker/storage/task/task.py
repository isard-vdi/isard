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
from os import environ, makedirs, remove, rename, walk
from os.path import basename, dirname, getmtime, isdir, isfile, join
from pathlib import Path
from re import search
from subprocess import PIPE, CalledProcessError, Popen, check_output, run
from time import sleep

from isardvdi_common.task import Task
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
    progress = 0.0
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
                "-f",
                "qcow2",
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
            "-f",
            "qcow2",
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


def convert(source_disk_path, dest_disk_path, format, compression):
    """
    Convert disk.


    :param source_disk_path: Path of the original file
    :type source_disk_path: str
    :param dest_disk_path: Path of the destination file
    :type dest_disk_path: str
    :param format: Format of the destination file. Supported formats: qcow2, vmdk
    :type format: str
    :param compression: True to compress the destination file. Only supported for qcow and qcow2 formats.
    :type compression: bool
    :return: Exit code of qemu-img command
    :rtype: int
    """
    format = format.lower()

    if format not in ["qcow2", "vmdk"]:
        raise ValueError(f"{format} is not a valid disk format.")

    if compression and format == "qcow2":
        compress = ["-c"]
    else:
        compress = []

    return run_with_progress(
        [
            "qemu-img",
            "convert",
            "-p",
            *compress,
            "-O",
            format,
            source_disk_path,
            dest_disk_path,
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


def find(storage_id, storage_path):
    """
    Find storage path from storage_id recursively in base_path.
    It assumes any isard-storage will have all mountpoints in /isard.

    :param storage_id: Storage ID
    :type storage_id: str
    :return: List of dicts with storage path, modified time, and qemu-img info backing chain
    :rtype: list
    """
    root_dir = "/isard"
    matching_files = []
    status = "deleted"
    for root, _, files in walk(root_dir):
        for filename in files:
            if storage_id in filename:
                file_path = join(root, filename)
                try:
                    modified_time = getmtime(file_path)
                except OSError:
                    modified_time = None
                # Skip if the file is not a qcow2 file or it is a hidden file (starts with a dot)
                if not file_path.endswith(".qcow2") or basename(file_path).startswith(
                    "."
                ):
                    storage_data = None
                else:
                    storage_data = qemu_img_info_backing_chain(storage_id, file_path)
                matching_files.append(
                    {
                        "path": file_path,
                        "mtime": modified_time,
                        "storage_data": storage_data,
                    }
                )
                if storage_path == file_path:
                    status = storage_data["status"]
    return {"id": storage_id, "status": status, "matching_files": matching_files}


def touch(path):
    """
    Update the access and modification times of a file.

    :param path: Path to file
    :type path: str
    """
    if isfile(path):
        Path(path).touch()


def sparsify(storage_path):
    """
    Sparsify disk
    `du` is used to get the actual disk usage of the file instead of the apparent size.

    :param storage_path: Path to disk
    :type storage_id: str
    :return: Exit code of virt-sparsify command and saved space
    :rtype: dict
    """
    try:
        # Get the current size of the disk
        old_size = run(
            [
                "du",
                "-s",
                storage_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        old_size = old_size.split("\t")[0]  # Extract the size from the output
    except:
        old_size = 0

    try:
        # Sparsify the disk
        result = run(
            [
                "virt-sparsify",
                "--in-place",
                storage_path,
            ],
            capture_output=True,  # Capture stdout and stderr
            text=True,  # Decode output as text
            check=True,  # Raise CalledProcessError on failure
        )
    except CalledProcessError as cpe:
        # Return error details, including captured stderr
        return (
            f"Error: Command failed with return code {cpe.returncode}. "
            f"stderr: {cpe.stderr.strip() or 'No error message provided.'}"
        )
    except Exception as e:
        # Handle other exceptions
        return f"Error: {str(e)}"

    try:
        # Get the new size of the disk
        new_size = run(
            [
                "du",
                "-s",
                storage_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        new_size = new_size.split("\t")[0]  # Extract the size from the output
    except:
        new_size = 0

    return {
        "exit_code": result.returncode,
        "saved_space": int(old_size) - int(new_size),
        "old_size": old_size,
        "new_size": new_size,
    }


def disconnect(storage_path):
    """
    Disconnect storage_id from backing file

    :param storage_id: Storage ID
    :type storage_id: str
    :return: Exit code of qemu-img command
    :rtype: int
    """
    disconnected_path = storage_path + ".wo_chain"

    try:
        convert = run(
            [
                "qemu-img",
                "convert",
                "-f",
                "qcow2",
                "-O",
                "qcow2",
                storage_path,
                disconnected_path,
            ],
            check=True,
        )
        if convert.returncode == 0:
            remove(storage_path)
            rename(disconnected_path, storage_path)
        else:
            remove(disconnected_path)

        return convert.returncode
    except Exception as e:
        return f"Error: {str(e)}"
