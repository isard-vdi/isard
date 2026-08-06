#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the engine -> hypervisor remote-command contract.

The engine drives parts of the hypervisor over SSH by invoking executables
that live in *this* component's image. Nothing in either component's own
imports covers that edge, so a rename on the hypervisor side used to break
GPU profile changes at runtime with a green pipeline: the engine only finds
out when the remote command exits non-zero on a real host.

The guard lives on the hypervisor side because this is the component that
owns the console scripts, and because its suite runs from the host with the
whole repo tree available. The engine suite runs inside the ``isard-engine``
container, which only holds a copy of ``engine/engine``: from there neither
``docker/hypervisor/pyproject.toml`` nor the uv workspace root exists.

This test reads both sides as text and asserts every remote console script
the engine calls is actually declared by ``isardvdi-hypervisor``.
"""

import re
import tomllib
from pathlib import Path


def _workspace_root() -> Path:
    """Walk up to the uv workspace root, the only path that sees every component."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "uv.lock").is_file():
            return candidate
    raise RuntimeError("uv workspace root not found above this test")


_HYP_SOURCE = _workspace_root() / "engine" / "engine" / "engine" / "models" / "hyp.py"
_HYPERVISOR_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# Matches the absolute venv path the engine must use over SSH, because a
# non-login shell does not inherit the hypervisor image's PATH.
_REMOTE_SCRIPT = re.compile(r"/\.venv/bin/(isardvdi-hypervisor[a-z0-9-]*)")


def _declared_scripts() -> set[str]:
    data = tomllib.loads(_HYPERVISOR_PYPROJECT.read_text())
    return set(data.get("project", {}).get("scripts", {}))


def test_hypervisor_pyproject_is_reachable():
    """The guard is worthless if it silently degrades into a no-op."""
    assert _HYPERVISOR_PYPROJECT.is_file(), (
        f"{_HYPERVISOR_PYPROJECT} not found: this suite needs the full repo "
        "tree, otherwise the engine->hypervisor contract goes unchecked"
    )


def test_remote_commands_resolve_to_declared_console_scripts():
    called = set(_REMOTE_SCRIPT.findall(_HYP_SOURCE.read_text()))
    assert (
        called
    ), "no remote hypervisor command found in hyp.py — did the invocation move?"

    unknown = sorted(called - _declared_scripts())
    assert not unknown, (
        "hyp.py invokes hypervisor console scripts that isardvdi-hypervisor "
        f"does not declare: {unknown}. Add them to [project.scripts] in "
        "docker/hypervisor/pyproject.toml or fix the engine call site."
    )


def test_no_legacy_script_paths_remain():
    """The pre-package layout shipped loose modules under /src/lib."""
    offenders = [
        line.strip()
        for line in _HYP_SOURCE.read_text().splitlines()
        if "/src/lib/" in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        "hyp.py still calls the hypervisor's pre-package script paths; these "
        f"no longer exist inside the image: {offenders}"
    )
