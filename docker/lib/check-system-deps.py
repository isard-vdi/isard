#!/usr/bin/env python3
"""Check that each Dockerfile's apk/dnf install list matches its pyproject.toml
[tool.isardvdi.system-deps] declarations.

Exit codes:
  0 -> all components coherent
  1 -> mismatch detected
  2 -> script error (parse failure, missing file)
"""
from __future__ import annotations

import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]

# (dockerfile path, pyproject path, kind)
# kind: "alpine" -> expects apk-build/apk-runtime
# kind: "fedora" -> expects dnf-build/dnf-runtime
COMPONENTS: list[tuple[str, str, str]] = [
    ("component/apiv4/docker/Dockerfile", "component/apiv4/pyproject.toml", "alpine"),
    (
        "component/changefeed/docker/Dockerfile",
        "component/changefeed/pyproject.toml",
        "alpine",
    ),
    (
        "component/change-handler/docker/Dockerfile",
        "component/change-handler/pyproject.toml",
        "alpine",
    ),
    (
        "component/socketio/docker/Dockerfile",
        "component/socketio/pyproject.toml",
        "alpine",
    ),
    (
        "component/openapi/docker/Dockerfile",
        "component/openapi/pyproject.toml",
        "alpine",
    ),
    (
        "component/core_worker/docker/Dockerfile",
        "component/core_worker/pyproject.toml",
        "alpine",
    ),
    ("engine/docker/Dockerfile", "engine/pyproject.toml", "alpine"),
    ("webapp/docker/Dockerfile", "webapp/pyproject.toml", "alpine"),
    ("notifier/docker/Dockerfile", "notifier/pyproject.toml", "alpine"),
    ("scheduler/docker/Dockerfile", "scheduler/pyproject.toml", "alpine"),
    ("docker/hypervisor/Dockerfile", "docker/hypervisor/pyproject.toml", "alpine"),
    ("docker/vpn/Dockerfile", "docker/vpn/pyproject.toml", "alpine"),
    ("docker/storage/Dockerfile", "docker/storage/pyproject.toml", "fedora"),
    ("docker/backupninja/Dockerfile", "docker/backupninja/pyproject.toml", "alpine"),
]

APK_RE = re.compile(r"apk add(?:\s+--[\w-]+(?:=\S+)?)*\s+(.+?)(?:&&|$)", re.MULTILINE)
DNF_RE = re.compile(r"dnf install(?:\s+-\S+)*\s+(.+?)(?:&&|$)", re.MULTILINE)


def parse_pkg_list(raw: str) -> set[str]:
    tokens = raw.replace("\\\n", " ").split()
    return {t for t in tokens if not t.startswith("-") and t not in {"y"}}


def extract_dockerfile_packages(
    path: pathlib.Path, kind: str
) -> tuple[set[str], set[str]]:
    content = path.read_text().replace("\\\n", " ")
    pattern = APK_RE if kind == "alpine" else DNF_RE
    build_pkgs: set[str] = set()
    runtime_pkgs: set[str] = set()
    for match in pattern.finditer(content):
        pkgs = parse_pkg_list(match.group(1))
        # Convention: first install in a builder stage is build, last in runtime stage is runtime.
        # We distinguish by scanning stage names.
        stage_line_start = content.rfind("FROM ", 0, match.start())
        stage_line_end = content.find("\n", stage_line_start)
        stage_line = (
            content[stage_line_start:stage_line_end] if stage_line_start >= 0 else ""
        )
        if "AS builder" in stage_line or "as builder" in stage_line:
            build_pkgs |= pkgs
        elif "AS runtime" in stage_line or "as runtime" in stage_line:
            runtime_pkgs |= pkgs
    return build_pkgs, runtime_pkgs


def extract_declared(path: pathlib.Path, kind: str) -> tuple[set[str], set[str]]:
    data = tomllib.loads(path.read_text())
    sd = data.get("tool", {}).get("isardvdi", {}).get("system-deps", {})
    if kind == "alpine":
        return set(sd.get("apk-build", [])), set(sd.get("apk-runtime", []))
    return set(sd.get("dnf-build", [])), set(sd.get("dnf-runtime", []))


def main() -> int:
    failures: list[str] = []
    for df, pj, kind in COMPONENTS:
        df_path = ROOT / df
        pj_path = ROOT / pj
        if not df_path.exists() or not pj_path.exists():
            failures.append(f"[missing] {df} or {pj}")
            continue
        df_build, df_runtime = extract_dockerfile_packages(df_path, kind)
        pj_build, pj_runtime = extract_declared(pj_path, kind)
        if df_build != pj_build:
            failures.append(f"[{df}] build mismatch: dockerfile={df_build ^ pj_build}")
        if df_runtime != pj_runtime:
            failures.append(
                f"[{df}] runtime mismatch: dockerfile={df_runtime ^ pj_runtime}"
            )
    if failures:
        print("\n".join(failures))
        return 1
    print("All components coherent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
