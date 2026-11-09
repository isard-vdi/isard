# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read the damage out of an ``e2fsck -fn`` run on a guest's mounted root."""

from __future__ import annotations

#: what a mounted ext4 keeps in memory, and the one prompt that answers each
FSCK_BENIGN = {
    "count wrong": "Fix?",
    "Padding at end": "Fix?",
    "orphan_present is set but orphan file is clean": "Clear?",
}


def fsck_damage(out: str) -> tuple[str, list[str]]:
    """``(rc, damage)`` of ``e2fsck -fn ...; echo rc=$?``; a benign finding is not damage."""
    code, damage, answer = "?", [], None
    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("rc="):
            code = line[3:]
            continue
        if answer and line.startswith(answer):
            answer = None
            continue
        prompt = next((p for m, p in FSCK_BENIGN.items() if m in line), None)
        if prompt:
            answer = None if prompt in line else prompt
            continue
        answer = None
        if "?" in line or "error" in line.lower():
            damage.append(line)
    return code, damage
