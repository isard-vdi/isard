# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every container whose code talks to Redis gets ``REDIS_PASSWORD``.

The code a part runs is what its ``<part>.devel.yml`` bind-mounts.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PARTS = ROOT / "docker-compose-parts"
COMMON = ROOT / "component" / "_common" / "src"

_MOUNT = re.compile(r"\$\{BUILD_ROOT_PATH\}/([^:\s]+):")
_DECLARED = re.compile(r"^\s*-?\s*REDIS_PASSWORD\s*[:=]", re.M)
_PY_CLIENTS = {"redis", "rq", "hiredis"}
_GO_CLIENT = re.compile(
    r'"(github\.com/redis/go-redis/[^"]*|[^"]*/isardvdi/pkg/redis)"'
)
_SHELL_CLIENT = re.compile(r"\bredis-cli\b")


def _is_test(path):
    return (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name.endswith(("_test.py", "_test.go"))
    )


def _imports(path, package=""):
    """Absolute names of every module the file imports, at any depth."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def _talks_to_redis(names):
    return any(name.split(".")[0] in _PY_CLIENTS for name in names)


def _common_modules_reaching_redis():
    graph = {}
    for path in COMMON.rglob("*.py"):
        if _is_test(path):
            continue
        parts = path.relative_to(COMMON).with_suffix("").parts
        module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        package = ".".join(parts[:-1])
        graph[module] = _imports(path, package)
    reaching = {m for m, names in graph.items() if _talks_to_redis(names)}
    grown = True
    while grown:
        grown = False
        for module, names in graph.items():
            if module not in reaching and names & reaching:
                reaching.add(module)
                grown = True
    return reaching


_REACHING = _common_modules_reaching_redis()


def _service_files(devel_part):
    """Files of the code the part runs, without the shared or generated trees."""
    files = []
    for mount in _MOUNT.findall(devel_part.read_text(encoding="utf-8")):
        if "isardvdi_common" in mount or "_client" in mount or mount.startswith("pkg"):
            continue
        source = ROOT / mount
        found = [source] if source.is_file() else source.rglob("*")
        files.extend(p for p in found if p.is_file() and not _is_test(p))
    return files


def _needs_redis(devel_part):
    for path in _service_files(devel_part):
        if path.suffix == ".py":
            names = _imports(path)
            if _talks_to_redis(names) or names & _REACHING:
                return True
        elif path.suffix == ".go":
            if _GO_CLIENT.search(path.read_text(encoding="utf-8", errors="replace")):
                return True
        elif path.suffix in {".sh", ""}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if _SHELL_CLIENT.search(text):
                return True
    return False


_DEVEL_PARTS = sorted(PARTS.glob("*.devel.yml"))
_REDIS_PARTS = [
    p.name.replace(".devel.yml", ".yml") for p in _DEVEL_PARTS if _needs_redis(p)
]


def test_the_discovery_finds_the_known_redis_clients():
    # A guard on the guard: if the discovery breaks, the test below would pass
    # over an empty list.
    assert "isardvdi_common.connections.redis_client" in _REACHING
    assert {"engine.yml", "apiv4.yml", "scheduler.yml"} <= set(_REDIS_PARTS)


@pytest.mark.parametrize("part", _REDIS_PARTS)
def test_every_redis_client_receives_the_password(part):
    text = (PARTS / part).read_text(encoding="utf-8")
    assert _DECLARED.search(text), (
        f"{part} runs code that connects to Redis but does not pass "
        "REDIS_PASSWORD; with the password build.sh always generates, the "
        "service fails with 'HELLO must be called with the client already "
        "authenticated'"
    )


_ADDRESSED_PARTS = sorted(
    p.name
    for p in PARTS.glob("*.yml")
    if re.search(r"^\s*-?\s*REDIS_HOST\s*[:=]", p.read_text(encoding="utf-8"), re.M)
)


@pytest.mark.parametrize("part", _ADDRESSED_PARTS)
def test_a_part_given_the_address_is_given_the_password(part):
    # Covers the parts without a devel source mount (storage-vdo-stats, ...).
    text = (PARTS / part).read_text(encoding="utf-8")
    assert _DECLARED.search(text), f"{part} passes REDIS_HOST but not REDIS_PASSWORD"


@pytest.mark.parametrize("part", _REDIS_PARTS)
def test_every_redis_client_receives_the_address(part):
    text = (PARTS / part).read_text(encoding="utf-8")
    for name in ("REDIS_HOST", "REDIS_PORT"):
        assert re.search(
            rf"^\s*-?\s*{name}\s*[:=]", text, re.M
        ), f"{part} must pass {name} with the password"
