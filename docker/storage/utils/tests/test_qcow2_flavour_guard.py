#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""build.sh must refuse a non-apiv4 flavour whose cfg still sets QCOW2_*, and
must NOT refuse an apiv4-bearing one.

isard-apiv4 is the only reader of QCOW2_* now, so those keys are inert on a
storage/hypervisor node -- the guard turns that silent trap into a build error.
But the guard's ``case`` matched literal spaces while the real ``$parts`` comes
straight from ``WEB_PARTS``/``ALLINONE_PARTS``, which are NEWLINE+TAB separated,
so it never saw ``apiv4`` and refused to build an ordinary web/all-in-one node.
This drives the REAL function seeded from the REAL parts strings, like
test_build_vdo_stats_guard.py does, so the whitespace bug is caught.
"""

import os
import re
import subprocess
from pathlib import Path

BUILD = Path(__file__).resolve().parents[4] / "build.sh"


def _run_guard(flavour, parts_var, **env):
    src = BUILD.read_text(encoding="utf-8")
    func = re.search(
        r"^_require_qcow2_only_on_apiv4\(\) \{\n.*?^\}\n", src, re.M | re.S
    ).group(0)
    parts_defs = "".join(
        re.search(rf'^{name}="[^"]*"\n', src, re.M).group(0)
        for name in ("ALLINONE_PARTS", "WEB_PARTS", "STORAGE_PARTS", "HYPERVISOR_PARTS")
    )
    script = (
        f'set -e\n{parts_defs}FLAVOUR="{flavour}"\nparts="${{{parts_var}}}"\n'
        f'{func}\n_require_qcow2_only_on_apiv4 "$FLAVOUR"\n'
    )
    return subprocess.run(
        ["sh", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **env},
    )


def test_web_flavour_with_qcow2_is_allowed():
    """The blocking bug: a normal web node with the recommended QCOW2_* set must
    build, not be refused because the guard couldn't find apiv4 in $parts."""
    r = _run_guard("web", "WEB_PARTS", QCOW2_CLUSTER_SIZE="128k")
    assert r.returncode == 0, r.stdout + r.stderr


def test_all_in_one_flavour_with_qcow2_is_allowed():
    r = _run_guard("all-in-one", "ALLINONE_PARTS", QCOW2_EXTENDED_L2="on")
    assert r.returncode == 0, r.stdout + r.stderr


def test_storage_flavour_with_qcow2_is_refused():
    r = _run_guard("storage", "STORAGE_PARTS", QCOW2_CLUSTER_SIZE="128k")
    assert r.returncode != 0
    assert "does not run apiv4" in r.stderr


def test_hypervisor_flavour_with_min_free_is_refused():
    # STORAGE_MIN_FREE_BYTES moved the same way; it must be guarded too.
    r = _run_guard("hypervisor", "HYPERVISOR_PARTS", STORAGE_MIN_FREE_BYTES="1073741824")
    assert r.returncode != 0


def test_storage_flavour_without_qcow2_is_allowed():
    r = _run_guard("storage", "STORAGE_PARTS")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_guard_is_actually_called():
    """The function is dead unless create_docker_compose_file invokes it;
    deleting the call must fail here."""
    src = BUILD.read_text(encoding="utf-8")
    assert re.search(r'_require_qcow2_only_on_apiv4 "\$FLAVOUR" \|\| exit 1', src)
