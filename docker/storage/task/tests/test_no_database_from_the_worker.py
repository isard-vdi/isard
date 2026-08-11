# SPDX-License-Identifier: AGPL-3.0-or-later

"""The storage worker must not carry the database into its process.

``isard-storage`` ships on nodes that have no ``isard-db``: the ``storage``,
``hypervisor`` and ``hypervisor-standalone`` flavours all include the storage
part and none of them includes the database one (``build.sh``). Any code path
that constructs a model there raises, and the ones that did cost every download
on every remote node.

Importing is where the regression would come back — a single
``from isardvdi_common.models.<x> import <X>`` re-opens it silently, and no
existing suite would notice: the connection pool is lazy, so nothing fails at
import time and the failure only surfaces on a node nobody runs tests on.

Run in a subprocess: ``sys.modules`` is process-global, and the rest of the
suite imports plenty of things this must not see.
"""

import json
import os
import subprocess
import sys

TASK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The one model the worker may hold: it is redis-backed (``RedisBase``).
ALLOWED_MODEL = "isardvdi_common.models.task"

PROBE = f"""
import sys, json
sys.path.insert(0, {TASK_DIR!r})
import task
banned = sorted(
    m
    for m in sys.modules
    if m == "rethinkdb"
    or m.startswith("rethinkdb.")
    or m.startswith("isardvdi_common.connections.rethink")
    or (m.startswith("isardvdi_common.models.") and m != {ALLOWED_MODEL!r})
)
print(json.dumps({{"banned": banned, "total": len(sys.modules)}}))
"""


def _probe():
    run = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=120
    )
    assert run.returncode == 0, f"the probe itself failed:\n{run.stderr}"
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_importing_the_worker_loads_no_database_module():
    result = _probe()

    assert result["banned"] == [], (
        "importing task pulled in database code: "
        + ", ".join(result["banned"])
        + " — the worker runs where there is no database to reach"
    )


def test_the_worker_still_holds_the_redis_backed_task_model():
    """Guards the guard: a probe that imported nothing would also pass."""
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {TASK_DIR!r}); import task;"
            f"print({ALLOWED_MODEL!r} in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().endswith("True")
