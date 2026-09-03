#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The vdo-stats image carries three files, and nothing else must be needed.

The common package stays out of the one container granted CAP_SYS_ADMIN, so an
import added upstream would break it at runtime and nowhere else.
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DOCKERFILE = ROOT / "docker" / "storage-vdo-stats" / "Dockerfile"

#: What the image installs beyond the standard library.
INSTALLED = {"redis"}


def copied_sources():
    """Repo-relative paths the Dockerfile COPYs, as {module path: source file}."""
    copied = {}
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^COPY\s+(\S+)\s+(\S+)\s*$", line.strip())
        if match:
            copied[match.group(2)] = ROOT / match.group(1)
    return copied


def module_name(destination):
    """The dotted name a copied file answers to under PYTHONPATH=/opt/isardvdi."""
    if not destination.startswith("/opt/isardvdi/"):
        return None
    relative = destination[len("/opt/isardvdi/") :]
    return relative[: -len(".py")].replace("/", ".")


def imported_names(source):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_the_dockerfile_copies_the_three_files_the_sidecar_runs():
    copied = copied_sources()
    assert sorted(Path(p).name for p in copied.values()) == [
        "physical_usage.py",
        "redis_urls.py",
        "storage-pool-physical",
    ]
    for source in copied.values():
        assert source.is_file(), f"{source} is COPYed but does not exist"


def test_every_import_is_stdlib_redis_or_another_copied_file():
    copied = copied_sources()
    available = {module_name(dest) for dest in copied} - {None}
    for destination, source in copied.items():
        for name in imported_names(source):
            root = name.split(".")[0]
            if root in sys.stdlib_module_names or root in INSTALLED:
                continue
            assert name in available, (
                f"{source.name} imports {name}, which the vdo-stats image does "
                f"not carry: copy it in the Dockerfile or keep it out of this "
                f"module"
            )
