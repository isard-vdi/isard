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

import logging
import os
import shlex
import shutil
import signal
import tempfile
import threading
import traceback
from contextlib import contextmanager
from functools import wraps
from json import loads
from os import environ, makedirs, remove, rename
from os import stat as os_stat
from os import walk
from os.path import basename, dirname, getmtime, isdir, isfile, join
from pathlib import Path
from re import search
from subprocess import (
    PIPE,
    CalledProcessError,
    Popen,
    TimeoutExpired,
    check_output,
    run,
)
from time import sleep, time

from isardvdi_common.helpers.task_cancel import TaskCancelWatcher
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.media import Media
from isardvdi_common.models.task import Task
from rq import get_current_job

log = logging.getLogger(__name__)

QEMU_IMG_TIMEOUT = 30  # seconds; prevents indefinite hangs on NFS

# Stream used to deliver task completion + progress events to
# isard-change-handler, which is the canonical consumer of the chain
# work that used to run on isard-core_worker. MAXLEN caps the stream
# at ~10k entries (approximate) so it doesn't grow unbounded when the
# consumer is briefly down.
TASK_RESULTS_STREAM = "stream:task-results"
TASK_RESULTS_STREAM_MAXLEN = 10000


def _publish_task_event(connection, *, kind, task_id, task_name, queue, **extra):
    """Best-effort XADD to ``stream:task-results``.

    The change-handler stream consumer is the canonical executor of the
    chain-handler work that used to live on isard-core_worker, and this
    XADD is the only signal it has. Failures are logged but never
    propagated so a transient Redis blip can't fail the underlying RQ
    task body.
    """
    try:
        fields = {
            "kind": kind,
            "task_id": task_id,
            "task_name": task_name,
            "queue": queue,
        }
        for k, v in extra.items():
            if v is None:
                continue
            fields[k] = str(v)
        connection.xadd(
            TASK_RESULTS_STREAM,
            fields,
            maxlen=TASK_RESULTS_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception:
        log.exception("Failed to XADD task-result event for %s", task_id)


def _publishes_result(func):
    """Decorator for storage-worker RQ task functions.

    Publishes a single ``kind=result`` event to ``stream:task-results``
    when the wrapped function returns (``job_status=finished``) or
    raises (``job_status=failed``). Re-raises the original exception so
    RQ's chain semantics are unchanged. A no-op outside an RQ context
    so unit tests that call the bare function still work.
    """
    task_name = func.__name__

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except BaseException:
            job = get_current_job()
            if job is not None:
                _publish_task_event(
                    job.connection,
                    kind="result",
                    task_id=job.id,
                    task_name=task_name,
                    queue=job.origin,
                    job_status="failed",
                )
            raise
        job = get_current_job()
        if job is not None:
            _publish_task_event(
                job.connection,
                kind="result",
                task_id=job.id,
                task_name=task_name,
                queue=job.origin,
                job_status="finished",
            )
        return result

    return wrapper


def _safe_unlink(path):
    """Best-effort removal of a partial file; never raises so cleanup can't
    mask the original error on a failing task's path."""
    try:
        if isfile(path):
            remove(path)
    except OSError:
        log.exception("could not remove file %s", path)


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

    if basename(file1) != basename(file2):
        return False

    try:
        stat1 = os_stat(file1)
        stat2 = os_stat(file2)
    except OSError:
        return False

    return stat1.st_mtime == stat2.st_mtime and stat1.st_size == stat2.st_size


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


def run_with_progress(command, extract_progress, on_progress=None, initial_check=None):
    """
    Run command reporting progress to RQ job metadata.

    :param command: Array of command arguments to be executed
    :type command: List of str
    :param extract_progress: Function to extract progress from stdout of command executed
    :type extrct_progress: Callable function with progress as firt parameter
    :param on_progress: Optional callback invoked with the rounded progress
        fraction (0.0–1.0) on each tick AND once with ``1.0`` on success.
        Used by ``move()`` to mirror the rsync percentage onto a Domain row's
        ``progress`` field so the user-facing templates list can render a
        progress bar the same way Media downloads do.
    :type on_progress: Callable[[float], None] | None
    :param initial_check: Optional one-shot callable invoked by
        :class:`TaskCancelWatcher` on entry to close the
        publish-before-subscribe race (see ``_media_aborting``). May be
        ``None`` when the cancel signal can only arrive *after* the
        subprocess is already running (the usual case for the
        ``abort-operations`` storage path).
    :type initial_check: Callable[[], bool] | None
    :return: Exit code of command executed
    :rtype: int
    :raises subprocess.CalledProcessError: returncode 130 if the run is
        cancelled mid-flight via :func:`request_task_cancel`. Raising (not
        returning the rc) is what makes RQ mark the job non-FINISHED so the
        chain's terminal ``update_status`` sees ``depending_status`` as
        canceled/failed and can flip the affected rows.
    """
    job = get_current_job()
    aborted = False
    # ``preexec_fn=os.setsid`` puts the child in its own process group so
    # SIGTERM via ``killpg`` reaches qemu-img/rsync (and any helpers they
    # fork) rather than just the immediate child.
    process = Popen(command, stdout=PIPE, preexec_fn=os.setsid)
    try:
        with TaskCancelWatcher(job.id, initial_check=initial_check) as watcher:
            while process.poll() is None:
                if watcher.cancelled:
                    aborted = True
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    break
                pct = round(extract_progress(process), 2)
                job.meta["progress"] = pct
                job.save_meta()
                # MR-2 of the core_worker retirement: the legacy per-tick
                # ``Queue("core").enqueue("task.feedback", …)`` is removed
                # — change-handler's stream consumer now emits the per-tick
                # SocketIO ``task`` event from this ``kind=progress`` XADD.
                _publish_task_event(
                    job.connection,
                    kind="progress",
                    task_id=job.id,
                    task_name=job.func_name.rsplit(".", 1)[-1],
                    queue=job.origin,
                    progress=pct,
                )
                if on_progress is not None:
                    try:
                        on_progress(pct)
                    except Exception:
                        log.exception("run_with_progress: on_progress callback failed")
                sleep(5)
                process.stdout.read1()
        try:
            process.wait(timeout=10)
        except TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    finally:
        if process.stdout:
            process.stdout.close()

    if aborted:
        raise CalledProcessError(returncode=130, cmd=command)
    if process.returncode == 0:
        job.meta["progress"] = 1
        job.save_meta()
        if on_progress is not None:
            try:
                on_progress(1.0)
            except Exception:
                log.exception("run_with_progress: final on_progress callback failed")
    return process.returncode


@contextmanager
def task_heartbeat(task_name, interval_s=30, timeout_s=None, **extra):
    """Emit a periodic structured log entry while a long task runs and
    publish a matching ``kind=progress`` event to ``stream:task-results``.

    Wraps the call site of long-running synchronous tasks (``sparsify``,
    ``virt_win_reg``, ``find`` full-walk) that don't go through
    ``run_with_progress``. For those tasks the operator gets nothing
    between start and end of the operation — making them indistinguishable
    from a stuck worker. This helper spawns a daemon thread that:

      - emits one log line every ``interval_s`` seconds with ``task``,
        ``job_id``, and ``elapsed_s`` fields, so Loki / log grep can show a
        clear "still alive" signal; and
      - publishes a ``kind=progress`` event to ``stream:task-results`` so
        the change-handler stream consumer fans out a ``task`` SocketIO
        event the webapp already renders as a progress bar. The
        ``progress`` value is the elapsed-time / timeout ratio, capped at
        ``0.95`` so the bar never reads 100% before the wrapped function
        actually returns (RQ's post-perform code then marks the Job
        ``FINISHED`` and ``Task.progress`` naturally returns 1.0).

    Both signals are best-effort: failures inside the heartbeat thread
    are swallowed so the wrapped operation can't be poisoned by a
    transient Redis blip or a logging hiccup.

    ``timeout_s`` defaults to the RQ job's configured timeout when not
    supplied; pass it explicitly when a callsite knows a tighter bound
    (e.g. an operation with an external SLA shorter than the queue
    default).

    Usage::

        with task_heartbeat("sparsify", storage_path=path, timeout_s=job.timeout):
            subprocess.run([...])
    """
    job = get_current_job()
    job_id = job.id if job else None
    if timeout_s is None and job is not None:
        # Fall back to the RQ job's own timeout. ``rq.Queue.DEFAULT_TIMEOUT``
        # is 180s in upstream RQ but per-callsite overrides are common
        # (sparsify uses 12h). The publish loop just clamps to ≤ 0.95 so
        # an under-estimated timeout caps the bar instead of skewing it.
        timeout_s = job.timeout
    start_t = time()
    stop = threading.Event()

    def _beat():
        while not stop.wait(interval_s):
            try:
                elapsed = time() - start_t
                log.info(
                    "task heartbeat: %s alive (elapsed %.1fs)",
                    task_name,
                    elapsed,
                    extra={
                        "task": task_name,
                        "job_id": job_id,
                        "elapsed_s": round(elapsed, 1),
                        **extra,
                    },
                )
                # Surface the same "still alive" signal to the UI via the
                # ``stream:task-results`` Redis stream consumed by
                # change-handler. Cap ``progress`` at 0.95 so the
                # progress bar can't read 100% before the wrapped task
                # actually returns — real completion bumps it to 1.0
                # through the ``kind=result`` path. If ``run_with_progress``
                # ever wraps one of these callsites and writes a real
                # progress meta value, defer to it.
                #
                # The XADD is open-coded (rather than calling the shared
                # ``_publish_task_event`` helper that ``_publishes_result``
                # uses) so this branch is self-contained — it lands
                # independently of the task-results-stream-consumer MR
                # chain. If both code paths converge later, the two XADD
                # shapes are identical (``stream:task-results``,
                # maxlen=10_000, approximate=True, the same field set).
                if job is not None and timeout_s:
                    real_progress = (job.meta or {}).get("progress", 0) or 0
                    pseudo_progress = min(0.95, elapsed / float(timeout_s))
                    if pseudo_progress > real_progress:
                        try:
                            fields = {
                                "kind": "progress",
                                "task_id": str(job_id or ""),
                                "task_name": str(task_name),
                                "queue": str(job.origin or ""),
                                "progress": str(pseudo_progress),
                            }
                            job.connection.xadd(
                                "stream:task-results",
                                fields,
                                maxlen=10000,
                                approximate=True,
                            )
                        except Exception:
                            # publish is best-effort: transient Redis
                            # errors, stream-not-yet-created on first
                            # boot, etc. — never let it surface to the
                            # worker. Heartbeat log line above still
                            # provides the operator signal.
                            pass
            except Exception:
                # heartbeat is best-effort; never let it leak from the worker
                pass

    thread = threading.Thread(target=_beat, daemon=True, name=f"heartbeat-{task_name}")
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


@_publishes_result
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
    # Cancel intentionally not wired: typically a thin clone (seconds).
    # If a future caller needs cancel for fully-allocated creation,
    # refactor from ``run()`` to Popen + ``run_with_progress``.
    if not isdir(dirname(storage_path)):
        makedirs(dirname(storage_path), exist_ok=True)
    # Idempotency: if the destination disk already exists, treat the
    # task as already done and return success. ``qemu-img create``
    # would otherwise fail with ``File exists`` on the second run, and
    # engine-restart recovery / manual re-trigger flows rely on being
    # able to re-enqueue the create chain safely. The downstream
    # ``qemu_img_info_backing_chain`` step still validates the file is
    # a valid qcow2 with the expected backing chain; corrupted /
    # mismatched files surface there as a clean Failed.
    if isfile(storage_path):
        log.info(
            "task.create: %s already exists, skipping qemu-img create (idempotent)",
            storage_path,
        )
        return 0
    backing_file = []
    if parent_path and parent_type:
        backing_file = ["-b", parent_path, "-F", parent_type]
    if size:
        size = [size]
    else:
        size = []

    options = ""
    if storage_type == "qcow2":
        cluster_size = environ.get("QCOW2_CLUSTER_SIZE", "4k")
        extended_l2 = environ.get("QCOW2_EXTENDED_L2", "off")
        lazy_refcounts = environ.get("QCOW2_LAZY_REFCOUNTS", "off")
        preallocation = environ.get("QCOW2_PREALLOCATION", "off")

        if extended_l2 == "on":
            _s = cluster_size.upper().strip()
            _multipliers = {"K": 1024, "M": 1024**2}
            _num = int("".join(c for c in _s if c.isdigit()))
            _unit = "".join(c for c in _s if c.isalpha())
            if _num * _multipliers.get(_unit, 1) < 16384:
                raise ValueError(
                    f"QCOW2_CLUSTER_SIZE={cluster_size} is too small for extended_l2=on "
                    f"(minimum 16k). Either set QCOW2_CLUSTER_SIZE>=16k or QCOW2_EXTENDED_L2=off"
                )

        options = (
            f"cluster_size={cluster_size},"
            f"extended_l2={extended_l2},"
            f"lazy_refcounts={lazy_refcounts}"
        )

        # Add preallocation if no backing file, or if extended_l2 is on (which supports
        # preallocation with backing files via subcluster allocation bits)
        if not parent_path or extended_l2 == "on":
            options += f",preallocation={preallocation}"

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
        timeout=QEMU_IMG_TIMEOUT,
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
            timeout=QEMU_IMG_TIMEOUT,
        )
    )
    qemu_img_info_data.setdefault("backing-filename")
    qemu_img_info_data.setdefault("backing-filename-format")
    qemu_img_info_data.setdefault("full-backing-filename")
    return {"id": storage_id, "status": "ready", "qemu-img-info": qemu_img_info_data}


@_publishes_result
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

    try:
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
            timeout=QEMU_IMG_TIMEOUT,
        )
    except TimeoutExpired:
        log.error("qemu_img_info_backing_chain: timeout for %s", storage_path)
        return {"id": storage_id, "status": "broken_chain"}
    storage_data = {"id": storage_id}
    if completed_process.returncode == 0:
        storage_data["status"] = "ready"
        qemu_img_info_data = loads(completed_process.stdout)
        qemu_img_info_data[0].setdefault("backing-filename")
        qemu_img_info_data[0].setdefault("backing-filename-format")
        qemu_img_info_data[0].setdefault("full-backing-filename")
        storage_data["qemu-img-info"] = qemu_img_info_data[0]
    else:
        match = search(
            rb"^qemu-img: Could not open \'([^\']*)\': ", completed_process.stderr
        )
        if match is None:
            log.error(
                "qemu_img_info_backing_chain: unexpected stderr for %s: %s",
                storage_path,
                completed_process.stderr,
            )
            storage_data["status"] = "broken_chain"
        else:
            path = match.group(1).decode()
            if path == storage_path:
                storage_data["status"] = "deleted"
            else:
                try:
                    backing = (
                        qemu_img_info(storage_id, storage_path)
                        .get("qemu-img-info", {})
                        .get("backing-filename")
                    )
                    storage_data["status"] = (
                        "orphan" if path == backing else "broken_chain"
                    )
                except Exception:
                    storage_data["status"] = "broken_chain"

    return storage_data


_CURL_PROGRESS_KEYS = (
    "total_percent",
    "total",
    "received_percent",
    "received",
    "xferd_percent",
    "xferd",
    "speed_download_average",
    "speed_upload_average",
    "time_total",
    "time_spent",
    "time_left",
    "speed_current",
)

_DOWNLOAD_PROGRESS_FLUSH_SECONDS = 1.0


def _curl_progress_dict(line):
    """Parse a single curl progress meter line into the legacy 12-key dict.

    Curl's default progress meter prints whitespace-separated columns
    matching ``_CURL_PROGRESS_KEYS``. This mirrors the parser the engine's
    ``DownloadThread`` used to ship — kept identical so the frontend
    renders the same fields without any change.
    """
    values = line.split()
    if len(values) != len(_CURL_PROGRESS_KEYS):
        return None
    progress = dict(zip(_CURL_PROGRESS_KEYS, values))
    try:
        progress["total_percent"] = int(float(progress["total_percent"]))
        progress["received_percent"] = int(float(progress["received_percent"]))
    except ValueError:
        progress["total_percent"] = 0
        progress["received_percent"] = 0
    return progress


def _media_aborting(media_id):
    """Return True if the media row's status was flipped to DownloadAborting.

    This is the one-shot startup check used by ``TaskCancelWatcher`` to
    close the narrow race where apiv4 publishes the cancel signal before
    the worker subscribes. After startup, the pub/sub listener is the
    primary signal — no per-iteration rethink lookup.
    """
    try:
        return Media(media_id).status == "DownloadAborting"
    except Exception:
        # If the row vanished mid-flight, treat as abort.
        return True


def _domain_aborting(domain_id):
    """Same pattern as ``_media_aborting`` but for the domain table.

    The registry-download chain flips the row status to
    ``DownloadAborting`` when apiv4 cancels — the
    :class:`TaskCancelWatcher` checks this once on entry to close the
    pub/sub-before-subscribe race.
    """
    try:
        return Domain(domain_id).status == "DownloadAborting"
    except Exception:
        return True


def _run_curl_download(
    *,
    url,
    dest_path,
    headers,
    insecure_ssl,
    google_drive_cookie,
    flush_progress,
    is_aborting,
):
    """Run the curl download with live progress reporting and pub/sub
    cancellation. ``flush_progress`` and ``is_aborting`` are callbacks
    so the same body can drive media-row updates *or* domain-row
    updates without duplicating the curl plumbing.

    Returns ``True`` on success, raises ``CalledProcessError`` on
    failure (RQ marks the chain FAILED so the dependent
    ``update_status`` can flip the row terminal).
    """
    job = get_current_job()
    makedirs(dirname(dest_path), exist_ok=True)

    curl_cmd = ["curl"]
    if insecure_ssl:
        curl_cmd.append("-k")
    # Abort a genuinely STALLED transfer fast (avg below speed-limit B/s for
    # speed-time s) so a dead upstream does not hold the worker for the whole
    # job_timeout; and cap total curl runtime just under the RQ job_timeout so
    # a slow-but-progressing download ends with a clean curl error instead of
    # an RQ JobTimeoutException mid-write.
    speed_limit = int(os.environ.get("URL_DOWNLOAD_MIN_SPEED_BPS") or 1024)
    speed_time = int(os.environ.get("URL_DOWNLOAD_MIN_SPEED_TIME") or 60)
    curl_cmd.extend(
        ["--speed-limit", str(speed_limit), "--speed-time", str(speed_time)]
    )
    if job is not None and job.timeout:
        curl_cmd.extend(["--max-time", str(max(1, int(job.timeout) - 30))])
    curl_cmd.extend(
        [
            "-L",
            "--max-redirs",
            "5",
            "--connect-timeout",
            "30",
            "--no-netrc",
            "-o",
            dest_path,
        ]
    )
    if google_drive_cookie:
        curl_cmd.extend(["-b", google_drive_cookie])
    for h in headers or []:
        curl_cmd.extend(["-H", h])
    curl_cmd.append(url)

    process = Popen(
        curl_cmd,
        stdout=PIPE,
        stderr=PIPE,
        preexec_fn=os.setsid,
    )

    # Skip the two header lines curl prints before the progress meter.
    process.stderr.readline()
    process.stderr.readline()

    last_flush = 0.0
    line = ""
    aborted = False
    with TaskCancelWatcher(job.id, initial_check=is_aborting) as watcher:
        while process.poll() is None:
            if watcher.cancelled:
                aborted = True
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                break

            c = process.stderr.read(1)
            if not c:
                sleep(0.1)
                continue
            ch = c.decode("utf-8", errors="replace")
            if ch in ("\r", "\n"):
                progress = _curl_progress_dict(line)
                line = ""
                now = time()
                if progress and (now - last_flush) >= _DOWNLOAD_PROGRESS_FLUSH_SECONDS:
                    last_flush = now
                    try:
                        flush_progress(progress)
                    except Exception:
                        log.exception("download: failed to persist progress")
                    if progress.get("received_percent") is not None:
                        pct = progress["received_percent"] / 100.0
                        job.meta["progress"] = pct
                        job.save_meta()
                        # MR-2 of the core_worker retirement: the legacy
                        # ``Queue("core").enqueue("task.feedback", …)`` is
                        # removed — change-handler's stream consumer now
                        # emits the per-tick SocketIO ``task`` event from
                        # this ``kind=progress`` XADD.
                        _publish_task_event(
                            job.connection,
                            kind="progress",
                            task_id=job.id,
                            task_name=job.func_name.rsplit(".", 1)[-1],
                            queue=job.origin,
                            progress=pct,
                        )
                continue
            line += ch

        if not aborted and watcher.cancelled:
            aborted = True
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass

    process.wait(timeout=10)

    if aborted:
        try:
            os.unlink(dest_path)
        except OSError:
            pass
        raise CalledProcessError(returncode=130, cmd=curl_cmd)

    if is_aborting():
        try:
            os.unlink(dest_path)
        except OSError:
            pass
        raise CalledProcessError(returncode=130, cmd=curl_cmd)

    if process.returncode != 0:
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        log.error("download failed (rc=%s): %s", process.returncode, stderr.strip())
        try:
            os.unlink(dest_path)
        except OSError:
            pass
        raise CalledProcessError(
            returncode=process.returncode, cmd=curl_cmd, stderr=stderr
        )

    job.meta["progress"] = 1.0
    job.save_meta()
    return True


@_publishes_result
def download_url(
    media_id,
    url,
    dest_path,
    headers=None,
    insecure_ssl=False,
    google_drive_cookie=None,
):
    """Download a URL to ``dest_path`` reporting progress on the media row.

    Replaces the engine's SSH-to-hypervisor curl path with an RQ task on
    isard-storage. The curl invocation matches what
    ``engine/services/threads/download_thread.py`` used to issue. Progress
    is written live to ``Media(media_id).progress`` so the existing
    frontend keeps rendering the same fields (received / total_percent /
    speed_current / time_left). The single ``job.meta['progress']`` float
    is also kept up to date for the generic task panel.

    :param media_id: Media row id to update progress on
    :param url: Source URL (already validated by apiv4)
    :param dest_path: Absolute destination path under the media pool mount
    :param headers: List of ``"Header: value"`` strings to forward to curl
    :param insecure_ssl: When True, pass ``-k`` (mirrors
        ``URL_DOWNLOAD_INSECURE_SSL`` on the legacy engine path)
    :param google_drive_cookie: Path to a cookie jar file when ``url`` is a
        Google Drive sharing link (requires the upstream to issue a
        confirmation cookie). Optional; the regular curl branch handles
        ordinary URLs.
    :raises CalledProcessError: when curl exits non-zero (RQ marks the
        job FAILED → dependent ``update_status`` task flips media to
        ``DownloadFailed``)
    """
    job = get_current_job()
    makedirs(dirname(dest_path), exist_ok=True)

    curl_cmd = ["curl"]
    if insecure_ssl:
        curl_cmd.append("-k")
    curl_cmd.extend(
        [
            "-L",
            "--max-redirs",
            "5",
            "--connect-timeout",
            "30",
            "--no-netrc",
            "-o",
            dest_path,
        ]
    )
    if google_drive_cookie:
        curl_cmd.extend(["-b", google_drive_cookie])
    for h in headers or []:
        curl_cmd.extend(["-H", h])
    curl_cmd.append(url)

    log.info("download_url: media=%s dest=%s", media_id, dest_path)
    # Flip the row to Downloading so the user sees curl is now actually
    # running (the chain root shows DownloadStarting while queued).
    try:
        Media(media_id).status = "Downloading"
    except Exception:
        log.exception("download_url: failed to flip media %s to Downloading", media_id)

    def _flush(progress):
        Media(media_id).progress = progress

    _run_curl_download(
        url=url,
        dest_path=dest_path,
        headers=headers,
        insecure_ssl=insecure_ssl,
        google_drive_cookie=google_drive_cookie,
        flush_progress=_flush,
        is_aborting=lambda: _media_aborting(media_id),
    )

    return {
        "id": media_id,
        "path_downloaded": dest_path,
    }


@_publishes_result
def download_url_for_domain(
    domain_id,
    storage_id,
    url,
    dest_path,
    headers=None,
    insecure_ssl=False,
    google_drive_cookie=None,
):
    """Download a URL into the storage path of a registry-download desktop.

    Replaces the engine's deleted SSH-curl path for ``domains`` rows
    (the ``DownloadThread.table == "domains"`` branch in the
    pre-merge ``download_thread.py``). The chain that wraps this task
    looks like::

        storage.{pool}.low: download_url_for_domain
          -> storage.{pool}.low: qemu_img_info_backing_chain
            -> core: storage_update          # flips storage to ``ready``
              -> core: update_status         # FAILED/CANCELED → Failed

    On the success path ``storage_update`` calls
    ``_promote_domains_to_stopped`` which transitions the domain row
    from ``DownloadStarting`` / ``Downloading`` → ``Stopped``, mirroring
    the legacy "Downloaded → Stopped" pair the engine used to emit.

    Cancellation rides the same ``task:cancel:<id>`` pub/sub primitive
    used by media downloads. apiv4 sets ``Domain.status =
    DownloadAborting`` to cover the publish-before-subscribe race
    (the watcher's ``initial_check``).

    :param domain_id: Domain row id whose ``status`` / ``progress`` to update
    :param storage_id: Pre-allocated Storage row id (the row already
        exists with ``status="non_existing"``; ``qemu_img_info_backing_chain``
        flips it to ``ready`` after the file is on disk)
    :param url: Source URL (validated by apiv4)
    :param dest_path: Absolute path to write the qcow2 to (matches
        ``Storage(storage_id).path``)
    :raises CalledProcessError: when curl exits non-zero (RQ marks
        the job FAILED → dependent ``update_status`` flips domain +
        storage to ``Failed``)
    """
    log.info(
        "download_url_for_domain: domain=%s storage=%s dest=%s",
        domain_id,
        storage_id,
        dest_path,
    )
    try:
        Domain(domain_id).status = "Downloading"
    except Exception:
        log.exception(
            "download_url_for_domain: failed to flip domain %s to Downloading",
            domain_id,
        )

    def _flush(progress):
        Domain(domain_id).progress = progress

    _run_curl_download(
        url=url,
        dest_path=dest_path,
        headers=headers,
        insecure_ssl=insecure_ssl,
        google_drive_cookie=google_drive_cookie,
        flush_progress=_flush,
        is_aborting=lambda: _domain_aborting(domain_id),
    )

    return {
        "id": domain_id,
        "storage_id": storage_id,
        "path_downloaded": dest_path,
    }


@_publishes_result
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


@_publishes_result
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


@_publishes_result
def move(
    origin_path,
    destination_path,
    method,
    bwlimit=0,
    remove_source_file=True,
    progress_domain_id=None,
):
    """
    Move disk.

    :param origin_path: Path of the original file
    :type origin_path: str
    :param destination_path: Path of the destination file
    :type destination_path: str
    :param method: ``"mv"``, ``"rsync"``, or ``"auto"``. ``"auto"`` compares
        ``os.stat(dirname(...)).st_dev`` on both sides and picks ``mv`` when
        the directories share a filesystem (atomic rename, microseconds),
        otherwise ``rsync`` (cross-fs, with progress). On ``OSError`` during
        the probe it falls back to ``rsync`` — works cross-fs and creates the
        destination dir.
    :type method: str
    :param progress_domain_id: Optional Domain row id to receive a
        ``progress = {"total_percent", "received_percent"}`` field for every
        rsync tick (and a final 100 on success). Mirrors the
        ``Media.progress`` pattern that drives the existing list-page
        progress bars in old-frontend (``Media.vue``) and Vue 3
        (``MediaView.vue``). For the ``mv`` branch the file move is
        instantaneous, so progress is written once at completion. Has no
        effect when ``None``.
    :type progress_domain_id: str | None
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

    if method == "auto":
        try:
            src_dev = os_stat(dirname(origin_path)).st_dev
            dst_dev = os_stat(dirname(destination_path)).st_dev
            method = "mv" if src_dev == dst_dev else "rsync"
        except OSError as exc:
            log.warning(
                "move(auto): st_dev probe failed (%s); falling back to rsync",
                exc,
            )
            method = "rsync"

    on_progress = None
    if progress_domain_id is not None:

        def _flush_domain_progress(pct):
            percent_int = int(round(pct * 100))
            Domain(progress_domain_id).progress = {
                "total_percent": percent_int,
                "received_percent": percent_int,
            }

        on_progress = _flush_domain_progress

    if method == "mv":
        shutil.move(origin_path, destination_path)
        if on_progress is not None:
            try:
                on_progress(1.0)
            except Exception:
                log.exception("move(mv): on_progress callback failed")
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
            on_progress=on_progress,
        )
    else:
        raise ValueError(f"Invalid move method: {method}")


@_publishes_result
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


@_publishes_result
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

    try:
        rc = run_with_progress(
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
    except BaseException:
        # Cancel/crash leaves a partial destination; drop it and re-raise.
        _safe_unlink(dest_disk_path)
        raise
    if rc != 0:
        # run_with_progress returns a non-zero rc instead of raising; returning
        # it would publish job_status="finished" and mark a partial disk ready.
        _safe_unlink(dest_disk_path)
        raise CalledProcessError(returncode=rc, cmd="qemu-img convert")
    return rc


@_publishes_result
def delete(path):
    """
    Delete disk.

    :param path: Path to disk
    :type path: str
    """
    if isfile(path):
        remove(path)
        return

    parent = dirname(path)
    if isdir(parent):
        log.info(
            f"delete: {path} absent on a reachable mount, skipping",
        )
        return
    raise FileNotFoundError(f"delete: {path} parent directory unreachable")


@_publishes_result
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
    # Cancel intentionally not wired: virt-win-reg edits the disk in
    # place via guestfish; killing it mid-run can corrupt the registry
    # hive.
    try:
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(registry_patch.encode())
            fp.flush()
            with task_heartbeat("virt_win_reg", storage_path=storage_path):
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
        # Returning an error string publishes job_status="finished" for a
        # failed merge, marking the disk ready. Log stderr and re-raise.
        log.error(
            "virt-win-reg failed for %s (exit %s): %s",
            storage_path,
            cpe.returncode,
            (cpe.stderr or "").strip() or "No error message provided.",
        )
        raise


@_publishes_result
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
    # Cancel intentionally not wired: qemu-img resize is bounded by
    # ``QEMU_IMG_TIMEOUT``; killing a shrink mid-run risks truncating
    # live data inside the qcow2.
    try:
        return run(
            [
                "qemu-img",
                "resize",
                storage_path,
                f"+{increment}G",
            ],
            timeout=QEMU_IMG_TIMEOUT,
            check=True,  # Raise on a non-zero qemu-img rc
        ).returncode
    except Exception:
        # A returned value publishes job_status="finished", recording a failed
        # resize as success. Log and re-raise.
        log.exception("qemu-img resize failed for %s", storage_path)
        raise


@_publishes_result
def find(storage_id, storage_path, full_walk=False):
    """
    Find storage path from storage_id recursively in base_path.
    It assumes any isard-storage will have all mountpoints in /isard.

    When full_walk is False (default), checks the expected storage_path
    directly (O(1)) and returns immediately if found. Falls back to a
    full walk only when the file is missing from the expected path.
    When full_walk is True, always walks the entire /isard tree to
    discover duplicates, moved files, and invalid copies.

    :param storage_id: Storage ID
    :type storage_id: str
    :param storage_path: Expected storage path
    :type storage_path: str
    :param full_walk: Force a full filesystem walk
    :type full_walk: bool
    :return: Dict with storage id, status, and list of matching files
    :rtype: dict
    """
    # Cancel intentionally not wired: admin-only filesystem walk; the
    # fast path is O(1) and the full walk has no user-facing waiter.
    try:
        root_dir = "/isard"
        matching_files = []
        status = "deleted"

        # Fast path: check expected location directly (O(1) on NFS)
        if not full_walk and isfile(storage_path):
            try:
                modified_time = getmtime(storage_path)
            except OSError:
                modified_time = None
            if storage_path.endswith(".qcow2") and not basename(
                storage_path
            ).startswith("."):
                storage_data = qemu_img_info_backing_chain(storage_id, storage_path)
            else:
                storage_data = None
            matching_files.append(
                {
                    "path": storage_path,
                    "mtime": modified_time,
                    "storage_data": storage_data,
                }
            )
            if storage_data:
                status = storage_data["status"]
            return {
                "id": storage_id,
                "status": status,
                "matching_files": matching_files,
            }

        # Full walk: file not at expected path, or full_walk explicitly requested.
        # Heartbeat surfaces "still walking" while the recursive scan runs — on
        # large /isard trees this can take minutes and otherwise looks identical
        # to a stuck worker in the logs.
        with task_heartbeat("find", storage_id=storage_id, full_walk=full_walk):
            for root, _, files in walk(root_dir):
                for filename in files:
                    if storage_id in filename:
                        file_path = join(root, filename)
                        try:
                            modified_time = getmtime(file_path)
                        except OSError:
                            modified_time = None
                        # Skip if the file is not a qcow2 file or it is a hidden file (starts with a dot)
                        if not file_path.endswith(".qcow2") or basename(
                            file_path
                        ).startswith("."):
                            storage_data = None
                        else:
                            storage_data = qemu_img_info_backing_chain(
                                storage_id, file_path
                            )
                        matching_files.append(
                            {
                                "path": file_path,
                                "mtime": modified_time,
                                "storage_data": storage_data,
                            }
                        )
                        if storage_path == file_path and storage_data:
                            status = storage_data["status"]
            return {
                "id": storage_id,
                "status": status,
                "matching_files": matching_files,
            }
    except Exception:
        log.error(
            "task.find failed: storage_id=%s storage_path=%s full_walk=%s\n%s",
            storage_id,
            storage_path,
            full_walk,
            traceback.format_exc(),
        )
        raise


@_publishes_result
def touch(path):
    """
    Update the access and modification times of a file.

    :param path: Path to file
    :type path: str
    """
    if isfile(path):
        Path(path).touch()


def _get_disk_usage(path):
    """Return disk usage in 1K-blocks (int) using du -s."""
    result = run(
        ["du", "-s", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip().split("\t")[0])


def _format_size(kb):
    """Format size in 1K-blocks to human-readable string."""
    if kb < 1024:
        return f"{kb} KB"
    elif kb < 1024 * 1024:
        return f"{kb / 1024:.1f} MB"
    else:
        return f"{kb / (1024 * 1024):.2f} GB"


@_publishes_result
def sparsify(storage_path):
    """
    Sparsify disk
    `du` is used to get the actual disk usage of the file instead of the apparent size.

    :param storage_path: Path to disk
    :type storage_path: str
    :return: Exit code of virt-sparsify command and saved space
    :rtype: dict
    """
    # Cancel intentionally not wired: ``virt-sparsify --in-place``
    # modifies the qcow2 directly; killing it mid-run can leave the disk
    # corrupt.
    try:
        old_size = _get_disk_usage(storage_path)
    except Exception as e:
        log.warning(
            "Failed to get disk usage before sparsify for %s: %s", storage_path, e
        )
        old_size = 0

    log.info(
        "Starting sparsify: %s (disk usage: %s)",
        storage_path,
        _format_size(old_size),
    )

    try:
        with task_heartbeat("sparsify", storage_path=storage_path):
            result = run(
                ["virt-sparsify", "--in-place", storage_path],
                capture_output=True,
                text=True,
                check=True,
            )
        if result.stderr:
            log.info(
                "virt-sparsify stderr for %s: %s", storage_path, result.stderr.strip()
            )
    except CalledProcessError as cpe:
        # A returned value publishes job_status="finished", recording a failed
        # sparsify as success. Log and re-raise.
        log.error(
            "virt-sparsify failed for %s (exit %d): %s",
            storage_path,
            cpe.returncode,
            cpe.stderr.strip() if cpe.stderr else "No error message",
        )
        raise

    try:
        new_size = _get_disk_usage(storage_path)
    except Exception as e:
        log.warning(
            "Failed to get disk usage after sparsify for %s: %s", storage_path, e
        )
        new_size = 0

    saved = int(old_size) - int(new_size)
    log.info(
        "Sparsify complete: %s | before: %s | after: %s | saved: %s",
        storage_path,
        _format_size(old_size),
        _format_size(new_size),
        _format_size(saved) if saved >= 0 else f"-{_format_size(-saved)}",
    )

    return {
        "exit_code": result.returncode,
        "saved_space": saved,
        "old_size": old_size,
        "new_size": new_size,
    }


@_publishes_result
def disconnect(storage_path):
    """
    Disconnect storage_id from backing file

    :param storage_id: Storage ID
    :type storage_id: str
    :return: Exit code of qemu-img command
    :rtype: int
    """
    # Cancel intentionally not wired: single-layer qemu-img convert into
    # a sibling temp file followed by an atomic rename; the operation is
    # short and the temp-file cleanup on cancel would need its own logic.
    disconnected_path = storage_path + ".wo_chain"

    try:
        run(
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
    except BaseException:
        # A returned value publishes job_status="finished", recording a failed
        # disconnect as success. Clean the partial sibling and re-raise.
        _safe_unlink(disconnected_path)
        raise
    remove(storage_path)
    rename(disconnected_path, storage_path)
    return 0
