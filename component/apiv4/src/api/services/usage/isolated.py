# Usage consolidation, driven from the API in a child process
# SPDX-License-Identifier: AGPL-3.0-or-later
#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.

"""Run the usage consolidation in a child process, one at a time cluster-wide."""

import asyncio
import contextlib
import ctypes
import json
import logging
import os
import signal
import sys
import time
import uuid

from api.services.error import Error
from isardvdi_common.connections.redis_urls import rq_url
from redis.asyncio import Redis
from redis.exceptions import LockError, RedisError

log = logging.getLogger("apiv4")

LOCK_KEY = "lock:usage:consolidation"
# Renewed while the child runs, so it only outlives a holder that died.
LEASE_TTL = 60
LEASE_RENEW = 20
DEFAULT_TIMEOUT = 3600
_SOCKET_TIMEOUT = 5

RUNNER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "run_consolidation.py"
)

# Same values as run_consolidation.py.
EXIT_OK = 0
EXIT_REJECTED = 3

_PR_SET_PDEATHSIG = 1


class ConsolidationFailed(Exception):
    """The child crashed, was killed or returned no readable result."""


def consolidation_timeout() -> int:
    raw = os.environ.get("USAGE_CONSOLIDATION_TIMEOUT", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def _die_with_parent() -> None:
    """Runs in the child before exec: SIGKILL it if the API process dies."""
    try:
        ctypes.CDLL(None, use_errno=True).prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)
    except Exception:  # noqa: BLE001  (best effort; the lease still lapses)
        pass


def _child_argv(item_type, days, run_id) -> list:
    argv = [sys.executable, RUNNER, "--run-id", run_id]
    if item_type is not None:
        argv += ["--item-type", str(item_type)]
    if days is not None:
        argv += ["--days", str(int(days))]
    return argv


def _parse_summary(stdout: bytes) -> dict:
    for line in reversed(stdout.decode(errors="replace").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {}


async def _renew(lock) -> None:
    while True:
        await asyncio.sleep(LEASE_RENEW)
        try:
            await lock.reacquire()
        except (LockError, RedisError):
            log.warning(
                "usage consolidation: could not renew %s; another run may start",
                LOCK_KEY,
            )


async def _run_child(item_type, days, run_id, timeout) -> dict:
    proc = await asyncio.create_subprocess_exec(
        *_child_argv(item_type, days, run_id),
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # inherited: the child logs where the API logs
        preexec_fn=_die_with_parent,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise Error(
            "gateway_timeout",
            f"Usage consolidation did not finish in {timeout}s and was stopped",
            description_code="usage_consolidation_timeout",
        )
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise

    summary = _parse_summary(stdout)
    if proc.returncode == EXIT_OK and summary.get("ok"):
        return summary
    if proc.returncode == EXIT_REJECTED and summary.get("error"):
        raise Error(
            summary["error"],
            summary.get("description", ""),
            description_code=summary.get("description_code"),
        )
    if proc.returncode is not None and proc.returncode < 0:
        raise ConsolidationFailed(f"child killed by signal {-proc.returncode}")
    if summary.get("exception"):
        raise ConsolidationFailed(
            f"{summary['exception']}: {summary.get('message', '')}"
        )
    raise ConsolidationFailed(f"child exited with code {proc.returncode}")


async def consolidate_isolated(item_type=None, days=None) -> dict:
    """Raise 409 while another run holds the lease, 504 past the timeout."""
    run_id = uuid.uuid4().hex[:12]
    timeout = consolidation_timeout()
    conn = Redis.from_url(
        rq_url(), socket_timeout=_SOCKET_TIMEOUT, socket_connect_timeout=_SOCKET_TIMEOUT
    )
    lock = conn.lock(LOCK_KEY, timeout=LEASE_TTL, blocking=False)
    try:
        try:
            acquired = await lock.acquire()
        except RedisError as exc:
            raise Error(
                "internal_server",
                f"Could not reach the lock service for the usage consolidation ({type(exc).__name__})",
                description_code="lock_unavailable",
            )
        if not acquired:
            raise Error(
                "conflict",
                "A usage consolidation is already running; try again when it finishes",
                description_code="usage_consolidation_running",
            )
        renewer = asyncio.create_task(_renew(lock))
        start = time.monotonic()
        try:
            log.info(
                "usage consolidation %s: starting child (item_type=%s days=%s timeout=%ss)",
                run_id,
                item_type,
                days,
                timeout,
            )
            summary = await _run_child(item_type, days, run_id, timeout)
            log.info(
                "usage consolidation %s: done in %.1fs (inserted=%s failed_batches=%s child_max_rss=%sMiB)",
                run_id,
                time.monotonic() - start,
                summary.get("inserted"),
                summary.get("failed_batches"),
                summary.get("max_rss_mib"),
            )
            return summary
        finally:
            renewer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewer
            with contextlib.suppress(LockError, RedisError):
                await lock.release()
    finally:
        with contextlib.suppress(RedisError):
            await conn.aclose()
