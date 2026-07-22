# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pytest conftest for scheduler unit tests.

The production ``scheduler/__init__.py`` constructs ``Scheduler()``
at import time (line 56: ``app.scheduler = Scheduler()``), which
opens an rdb connection and seeds default jobs. Unit tests that
import any submodule (e.g. ``scheduler.lib.flask_rethink``) would
trigger the same construction path because Python has to initialise
the parent package first — and in a test rig with no live rdb,
``Scheduler.__init__`` hangs forever on the first ``db.conn`` read.

Stub a minimal ``scheduler`` package + Flask ``app`` BEFORE pytest
collects test files. The real package's submodules can still be
loaded individually via the path injection below; the production
``__init__.py`` is bypassed for the test process only.
"""

import os
import sys
import types
from pathlib import Path

# Make ``scheduler.lib`` importable as a real submodule package
# without going through ``scheduler/__init__.py``.
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _install_stub_scheduler_package():
    """Replace ``scheduler/__init__.py`` with a no-op stub that
    exposes a ``scheduler.app`` shim sufficient for the modules
    under ``scheduler.lib`` that import ``from scheduler import app``.

    The stub carries a real ``ModuleSpec`` so
    ``importlib.util.find_spec('scheduler')`` (used by
    ``tests/test_import.py``) keeps returning a non-None result —
    otherwise pinning the stub would break that pre-existing
    discoverability test.
    """
    if "scheduler" in sys.modules:
        # Real or already-stubbed; leave it alone.
        return

    import importlib.machinery

    pkg_path = str(_SRC_DIR / "scheduler")
    spec = importlib.machinery.ModuleSpec("scheduler", loader=None)
    spec.submodule_search_locations = [pkg_path]
    pkg = types.ModuleType("scheduler")
    pkg.__spec__ = spec
    pkg.__path__ = [pkg_path]
    pkg.app = None  # filled in lazily by tests that need it
    sys.modules["scheduler"] = pkg


_install_stub_scheduler_package()

# Don't let pytest accidentally import the production package init —
# our stub package above is the source of truth for the test process.
os.environ.setdefault("PYTEST_SCHEDULER_STUBBED", "1")
