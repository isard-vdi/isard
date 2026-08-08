#!/bin/sh
#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Run a test command with a real Redis, so `make ci-test-common` /
# `ci-test-change-handler` reproduce `unit-test-common` / `unit-test-change-handler`
# instead of silently skipping the suites that assert on Redis's own behaviour
# (the rq job graphs and the `ended_at` Lua stamp — see `.python-test-job-redis`
# in .gitlab-ci.yml). Those suites SKIP when there is no server, so a `ci-test-*`
# target that does not raise one goes green having asserted nothing.
#
# Two environments, one command:
#   - CI, or any dev who exports one: a Redis is already declared via
#     ISARD_TEST_REDIS / REDIS_HOST. We touch no docker — just run the command.
#     This is why the change is invisible to CI: its redis service is already
#     there, so this wrapper does nothing but pass the command through.
#   - A bare checkout (the gap this closes): we start the SAME digest-pinned
#     image the CI service uses, point the suites at it, and tear it down on the
#     way out, failures included.

set -eu

# Resolve repo root from this script's own location, so the image ref is read
# from the one .gitlab-ci.yml no matter the caller's cwd.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

# The skip-count gate. "0 failed" says nothing when a suite quietly skipped the
# tests that mattered, so when SKIP_GATE_REPORT names a junit xml we fail the
# run whenever its skip count differs from EXPECTED_SKIPS (default 0). A larger
# count is not automatically wrong — but it has to be declared on purpose, not
# drift in unnoticed. Returns the command's own status when the gate passes.
run_gate() {
    cmd_status="$1"
    [ -n "${SKIP_GATE_REPORT:-}" ] || return "$cmd_status"
    report="$SKIP_GATE_REPORT"
    case "$report" in
        /*) : ;;
        *) report="$repo_root/$report" ;;
    esac
    # No report means pytest never got far enough to write one; its own
    # non-zero status already tells that story.
    [ -f "$report" ] || return "$cmd_status"
    expected="${EXPECTED_SKIPS:-0}"
    # The first skipped="N" is the run-level total pytest writes on the
    # <testsuites>/<testsuite> root.
    skipped=$(grep -oE 'skipped="[0-9]+"' "$report" | head -n1 | grep -oE '[0-9]+' || true)
    skipped=${skipped:-0}
    if [ "$skipped" != "$expected" ]; then
        echo "" >&2
        echo "ci-with-redis: SKIP GATE — $report reports $skipped skipped, expected $expected." >&2
        echo "A suite that skips has proved nothing there. Give it what it needs to run," >&2
        echo "or set EXPECTED_SKIPS=$skipped to declare the count on purpose." >&2
        return 1
    fi
    echo "ci-with-redis: SKIP GATE ok — $skipped skipped == expected $expected ($report)." >&2
    return "$cmd_status"
}

# A Redis already declared (CI service, or a dev's own stack) — use it untouched.
if [ -n "${ISARD_TEST_REDIS:-}" ] || [ -n "${REDIS_HOST:-}" ]; then
    set +e
    "$@"
    status=$?
    run_gate "$status"
    exit $?
fi

# No Redis in the environment: raise the same image and digest the CI service
# pins, read from .gitlab-ci.yml rather than duplicated here so the two can
# never drift.
image=$(grep -oE 'redis:[0-9][A-Za-z0-9._-]*@sha256:[a-f0-9]+' "$repo_root/.gitlab-ci.yml" | head -n1)
if [ -z "$image" ]; then
    echo "ci-with-redis: could not read the redis image ref from .gitlab-ci.yml" >&2
    exit 1
fi

# Unique per invocation ($$ = this make's pid) so two concurrent `make`s on one
# host never collide on the name or the port, and so cleanup only ever removes
# the container THIS run started.
name="isard-ci-redis-$$"
started=""

cleanup() {
    if [ -n "$started" ]; then
        docker rm -f "$name" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

# -p 127.0.0.1::6379 asks the daemon for a free host port bound to loopback
# only. We never reuse a running server: we cannot know its db 9 is clean, and
# the suites flush the dbs they touch.
docker run -d --rm --name "$name" -p 127.0.0.1::6379 "$image" >/dev/null
started=1

port=$(docker port "$name" 6379/tcp | head -n1 | sed 's/.*://')
if [ -z "$port" ]; then
    echo "ci-with-redis: could not read the published port of $name" >&2
    exit 1
fi

# Wait for the server to answer before handing it to pytest — a fresh container
# is not accepting connections the instant `docker run` returns.
ready=""
i=0
while [ "$i" -lt 60 ]; do
    if docker exec "$name" redis-cli ping 2>/dev/null | grep -q PONG; then
        ready=1
        break
    fi
    i=$((i + 1))
    sleep 0.5
done
if [ -z "$ready" ]; then
    echo "ci-with-redis: redis container $name did not become ready in 30s" >&2
    exit 1
fi

# The suites read these three names between them: REDIS_HOST/REDIS_PORT for the
# rq_url() builder and the change-handler chain harness, ISARD_TEST_REDIS for
# the url-taking ones. db 9 matches the CI service's ISARD_TEST_REDIS.
export REDIS_HOST=127.0.0.1
export REDIS_PORT="$port"
export REDIS_PASSWORD=""
export ISARD_TEST_REDIS="redis://127.0.0.1:$port/9"

set +e
"$@"
status=$?
run_gate "$status"
exit $?
