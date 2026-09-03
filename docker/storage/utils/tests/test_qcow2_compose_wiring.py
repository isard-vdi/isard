#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The whole centralization rests on isard-apiv4 actually receiving the five
vars, and on the storage/engine containers NOT receiving them.

No other test asserts the compose wiring, so a rebase or merge resolution that
dropped the appended apiv4.yml lines would leave every install silently on the
defaults with a green suite. Pin the shape here.
"""

import re
from pathlib import Path

_PARTS = Path(__file__).resolve().parents[4] / "docker-compose-parts"
_VARS = (
    "QCOW2_CLUSTER_SIZE",
    "QCOW2_EXTENDED_L2",
    "QCOW2_LAZY_REFCOUNTS",
    "QCOW2_PREALLOCATION",
    "STORAGE_MIN_FREE_BYTES",
)


def _declares(part, var):
    text = (_PARTS / part).read_text(encoding="utf-8")
    return re.search(rf"^\s*{re.escape(var)}:", text, re.M) is not None


def test_apiv4_declares_all_five_vars():
    missing = [v for v in _VARS if not _declares("apiv4.yml", v)]
    assert not missing, f"apiv4.yml must declare {missing} -- the sole reader now"


def test_storage_and_engine_do_not_declare_the_geometry():
    leaked = [
        (part, v)
        for part in ("storage.yml", "engine.yml")
        for v in _VARS
        if _declares(part, v)
    ]
    assert not leaked, f"these must not carry the enqueuer-only policy: {leaked}"
