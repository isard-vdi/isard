# SPDX-License-Identifier: AGPL-3.0-or-later

"""A desktop's disk problems: quick fixes run at once, costly ones only when allowed."""

import logging

from api.services.error import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib import queue_estimate, queue_tiers
from isardvdi_common.lib.storage import problems
from isardvdi_common.lib.task_index import current_task_id
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task, tasks_from_ids

_CLUSTER = 65536


def _size(row):
    info = row.get("qemu-img-info")
    return (info.get("actual-size") or 0) if isinstance(info, dict) else 0


def _tier(fix, row):
    if fix == problems.CHECK:
        return queue_tiers.check_tier(_size(row) // _CLUSTER)
    if fix in (problems.REPAIR_LEAKS, problems.REPAIR_ALL):
        return queue_tiers.repair_tier(problems.FIXES[fix]["what"])
    if fix in (problems.DIG_HOLES, problems.SPARSIFY):
        return "maintenance"
    return "standard"


def _estimate(fix, row):
    task = problems.FIXES[fix]["task"]
    tier = _tier(fix, row)
    try:
        pool = StoragePool.get_best_for_action(task, path=row.get("directory_path")).id
        return queue_estimate.estimate_new(Task._redis, pool, tier, task, _size(row))
    except Exception:
        return {"tier": tier}


def _running_task(storage_id):
    task_id = current_task_id(Task._redis, storage_id)
    tasks = tasks_from_ids([task_id]) if task_id else []
    if not tasks or tasks[0].status in ("finished", "failed", "canceled"):
        return None
    task = tasks[0]
    estimate = queue_estimate.estimate_task(task)
    return {
        "id": task.id,
        "task": task.task,
        "status": task.status,
        "progress": task.progress,
        "position": estimate.get("effective_position"),
        "eta_seconds": estimate.get("eta_seconds"),
        "stranded": estimate.get("stranded"),
    }


def _description_code(error):
    return (getattr(error, "error", None) or {}).get("description_code") or (
        "internal_server"
    )


def _queue(fix, storage, row, user_id):
    if fix == problems.CHECK:
        return storage.check_integrity(user_id)
    if fix == problems.CHECK_CHAIN:
        return storage.check_backing_chain(user_id, priority=_tier(fix, row))
    if fix in (problems.REPAIR_LEAKS, problems.REPAIR_ALL):
        return storage.repair(
            user_id,
            problems.FIXES[fix]["what"],
            priority=_tier(fix, row),
            secondary_priority="high",
        )
    if fix == problems.DIG_HOLES:
        return storage.dig_holes(
            user_id, priority="low", secondary_priority="high", verify=True
        )
    return storage.sparsify(user_id, priority="default", secondary_priority="high")


class StorageProblemsService:
    @staticmethod
    def _desktop_disks(payload, desktop_id):
        Helpers.owns_domain_id(payload=payload, domain_id=desktop_id)
        domain = Domain(desktop_id)
        # owns_domain_id also admits a template shared through alloweds
        if domain.kind != "desktop" and payload.get("role_id") != "admin":
            raise Error(
                "forbidden",
                f"{desktop_id} is not a desktop",
                description_code="not_enough_rights_desktop",
            )
        disks = domain.create_dict.get("hardware", {}).get("disks", [])
        return [d["storage_id"] for d in disks if d.get("storage_id")]

    @staticmethod
    def report(payload: dict, desktop_id: str) -> dict:
        """Every disk of the desktop with its problems and who may fix each."""
        can_costly = Helpers.can_repair_storage_costly(payload)
        out = []
        for storage_id in StorageProblemsService._desktop_disks(payload, desktop_id):
            row = Storage.get(storage_id)
            if not row:
                out.append(
                    {
                        "storage_id": storage_id,
                        "problems": [{"code": "storage_missing", "mode": "admin"}],
                    }
                )
                continue
            marks = row.get("pending_actions") or {}
            found = []
            for problem in problems.diagnose(row):
                mode = problems.mode(problem)
                mark = problems.FIXES.get(problem.fix, {}).get("mark")
                found.append(
                    {
                        "code": problem.code,
                        "fix": problem.fix,
                        "blocks_start": problem.blocks_start,
                        "mode": mode,
                        "allowed": mode == "quick" or (mode == "costly" and can_costly),
                        "pending_since": (marks.get(mark) or {}).get("since"),
                        "estimate": (
                            _estimate(problem.fix, row) if problem.fix else None
                        ),
                    }
                )
            entry = {
                "storage_id": storage_id,
                "status": row.get("status"),
                "size": _size(row),
                "problems": found,
            }
            task = _running_task(storage_id)
            if task:
                entry["task"] = task
            out.append(entry)
        return {
            "desktop_id": desktop_id,
            "can_repair_costly": can_costly,
            "disks": out,
        }

    @staticmethod
    def handle(payload: dict, desktop_id: str) -> dict:
        """Queue each disk's first quick fix now and record the rest as pending actions."""
        runs = []
        for storage_id in StorageProblemsService._desktop_disks(payload, desktop_id):
            row = Storage.get(storage_id)
            if not row or _running_task(storage_id):
                continue
            wanted = {p.fix for p in problems.diagnose(row) if p.fix}
            queued = False
            for fix in problems.QUICK_ORDER:
                if fix not in wanted:
                    continue
                run = {"storage_id": storage_id, "fix": fix}
                if not queued:
                    try:
                        run["task_id"] = _queue(
                            fix, Storage(storage_id), row, payload.get("user_id")
                        )
                        queued = True
                    except Exception as e:
                        run["refused"] = _description_code(e)
                mark = problems.FIXES[fix]["mark"]
                if "task_id" not in run and mark:
                    Storage.flag_pending(
                        storage_id,
                        mark,
                        found_by=problems.FOUND_BY_INTERACTIVE,
                        if_absent=True,
                    )
                    run["recorded"] = mark
                runs.append(run)
        report = StorageProblemsService.report(payload, desktop_id)
        report["quick_fixes"] = runs
        return report

    @staticmethod
    def handle_quietly(payload: dict, desktop_id: str) -> None:
        """``handle`` for a start that failed on its disks: it never masks the start error."""
        try:
            StorageProblemsService.handle(payload, desktop_id)
        except Exception:
            logging.warning(
                "Could not handle the disk problems of desktop %s",
                desktop_id,
                exc_info=True,
            )

    @staticmethod
    def fix(payload: dict, desktop_id: str, storage_id: str, fix: str) -> dict:
        """Queue ``fix`` on one of the desktop's disks; a costly one needs the permission."""
        if storage_id not in StorageProblemsService._desktop_disks(payload, desktop_id):
            raise Error(
                "not_found", f"Storage {storage_id} is not a disk of {desktop_id}"
            )
        if problems.is_costly(fix) and not Helpers.can_repair_storage_costly(payload):
            raise Error(
                "forbidden",
                f"Only an administrator or an allowed user may run {fix}",
                description_code="storage_repair_not_allowed",
            )
        row = Storage.get(storage_id) or {}
        if fix not in {p.fix for p in problems.diagnose(row) if p.fix}:
            raise Error(
                "precondition_required",
                f"Storage {storage_id} has no problem that {fix} answers",
                description_code="storage_fix_not_needed",
            )
        if _running_task(storage_id):
            raise Error(
                "precondition_required",
                f"Storage {storage_id} already has a task in progress",
                description_code="storage_fix_in_progress",
            )
        task_id = _queue(fix, Storage(storage_id), row, payload.get("user_id"))
        return {"task_id": task_id, "estimate": _estimate(fix, row)}
