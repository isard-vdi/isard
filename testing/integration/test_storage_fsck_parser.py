# SPDX-License-Identifier: AGPL-3.0-or-later

"""The fsck reading of the chain safety test: what a mounted root always shows is not damage."""

from __future__ import annotations

import pytest

from .helpers.fsck import fsck_damage

pytestmark = [pytest.mark.real]

HEAD = "e2fsck 1.47.2 (1-Jan-2025)\nWarning!  /dev/vda1 is mounted.\n"
PASSES = (
    "Pass 1: Checking inodes, blocks, and sizes\n"
    "Pass 2: Checking directory structure\n"
    "Pass 3: Checking directory connectivity\n"
    "Pass 4: Checking reference counts\n"
    "Pass 5: Checking group summary information\n"
)
COUNTERS = (
    "Free blocks count wrong (512345, counted=512301).\nFix? no\n\n"
    "Free inodes count wrong (131012, counted=131008).\nFix? no\n\n"
)
ORPHAN = "Feature orphan_present is set but orphan file is clean.\nClear? no\n\n"


@pytest.mark.parametrize(
    "out",
    [
        HEAD + PASSES + COUNTERS + "rc=4\n",
        HEAD + ORPHAN + PASSES + COUNTERS + "rc=0\n",
        HEAD + ORPHAN.replace(".\nClear?", ".  Clear?") + PASSES + "rc=0\n",
    ],
    ids=["summary-counters", "debian13-orphan-file", "orphan-answer-on-one-line"],
)
def test_what_a_mounted_root_always_shows_is_not_damage(out):
    code, damage = fsck_damage(out)
    assert damage == []
    assert code in ("0", "4")


@pytest.mark.parametrize(
    "finding",
    [
        "Inode 1234 has illegal block(s).  Clear? no\n",
        "Inode 1234 has illegal block(s).\nClear? no\n",
        "Feature orphan_present is set but orphan file is clean.\n"
        "Entry 'x' in / (2) has deleted/unused inode 99.  Clear? no\n",
        "Feature orphan_present is set but orphan file is clean.\nFix? no\n",
        "Free blocks count wrong (1, counted=2).\nClear? no\n",
    ],
    ids=[
        "illegal-blocks",
        "illegal-blocks-two-lines",
        "damage-right-after-the-orphan-note",
        "orphan-note-answered-by-another-prompt",
        "counter-answered-by-another-prompt",
    ],
)
def test_real_damage_is_still_damage(finding):
    _code, damage = fsck_damage(HEAD + PASSES + finding + "rc=4\n")
    assert damage
