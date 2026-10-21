#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which disk files may give back their zero blocks (``fallocate --dig-holes``)."""

import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional

DELETED_DIR = "/deleted/"
# A disk that changed status this recently may still be part of an operation.
DEFAULT_SETTLE_SECONDS = 3600
STOPPED_DESKTOP_STATUSES = frozenset({"Stopped", "Failed"})


@dataclass
class Candidate:
    storage_id: str
    path: str
    role: str  # template | backing | desktop
    apparent: int = 0
    allocated: int = 0
    data: Optional[int] = None
    reason: Optional[str] = None  # set when the disk is NOT eligible
    domains: List[str] = field(default_factory=list)

    @property
    def reclaimable(self) -> int:
        if self.data is None:
            return 0
        return max(0, self.allocated - self.data)


def storage_path(storage: dict) -> Optional[str]:
    directory = storage.get("directory_path")
    if not directory or not storage.get("id"):
        return None
    return os.path.join(directory, f"{storage['id']}.{storage.get('type') or 'qcow2'}")


def disk_owners(domains: Iterable[dict]) -> Dict[str, List[dict]]:
    """storage_id -> the domains that list it among their disks."""
    owners: Dict[str, List[dict]] = {}
    for domain in domains or []:
        disks = ((domain.get("create_dict") or {}).get("hardware") or {}).get(
            "disks"
        ) or []
        for disk in disks:
            sid = disk.get("storage_id") if isinstance(disk, dict) else None
            if sid:
                owners.setdefault(sid, []).append(domain)
    return owners


def parents_with_children(storages: Iterable[dict]) -> set:
    """Ids of the storages some other storage reads through, deleted ones too."""
    return {s["parent"] for s in storages or [] if s.get("parent")}


def classify(
    storages: Iterable[dict],
    domains: Iterable[dict],
    now: float,
    settle_seconds: int = DEFAULT_SETTLE_SECONDS,
) -> List[Candidate]:
    """Every storage with a file path, eligible or not; ``reason`` says why not."""
    storages = list(storages or [])
    owners = disk_owners(domains)
    parents = parents_with_children(storages)
    out = []
    for s in storages:
        path = storage_path(s)
        if not path:
            continue
        doms = owners.get(s["id"], [])
        if s["id"] in parents:
            role = "backing"
        elif any(d.get("kind") == "template" for d in doms):
            role = "template"
        else:
            role = "desktop"
        c = Candidate(
            storage_id=s["id"],
            path=path,
            role=role,
            domains=[d.get("id") for d in doms],
        )
        live_desktops = [
            d
            for d in doms
            if d.get("kind") != "template"
            and d.get("status") not in STOPPED_DESKTOP_STATUSES
        ]
        if s.get("status") != "ready":
            c.reason = f"status {s.get('status')}"
        elif "w" not in (s.get("perms") or ["w"]):
            c.reason = "read-only disk"
        elif not doms:
            c.reason = "no domain uses it"
        elif role == "template":
            c.reason = "a template uses it"
        elif live_desktops:
            c.reason = "a desktop using it is not stopped"
        elif role == "backing":
            c.reason = "has descendants"
        elif DELETED_DIR in path:
            c.reason = "parked in deleted/"
        elif now - float(s.get("status_time") or 0) < settle_seconds:
            c.reason = "changed status less than the settle time ago"
        out.append(c)
    return out


def measure(candidate: Candidate, qemu_img: str = "qemu-img") -> Candidate:
    """Fill apparent/allocated from stat and data from ``qemu-img map``."""
    st = os.stat(candidate.path)
    candidate.apparent = st.st_size
    candidate.allocated = st.st_blocks * 512
    try:
        out = subprocess.run(
            [qemu_img, "map", "-U", "--output=json", candidate.path],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        ).stdout
        candidate.data = sum(
            e["length"]
            for e in json.loads(out)
            if e.get("data") and not e.get("zero") and e.get("depth", 0) == 0
        )
    except (subprocess.SubprocessError, ValueError, KeyError, OSError):
        candidate.data = None
    return candidate


def as_report_row(candidate: Candidate) -> dict:
    row = asdict(candidate)
    row["reclaimable"] = candidate.reclaimable
    return row
