# SPDX-License-Identifier: AGPL-3.0-or-later
"""The usage consolidation runs in a child process, one run at a time."""

import json
import os
import subprocess
import sys
import textwrap

import pytest
from api.services.error import Error
from api.services.usage import isolated
from redis.exceptions import ConnectionError as RedisConnectionError


class _FakeLock:
    def __init__(self, store, name, timeout):
        self.store, self.name, self.timeout = store, name, timeout
        self.token = None

    async def acquire(self):
        if self.store.get("down"):
            raise RedisConnectionError("down")
        if self.name in self.store["held"]:
            return False
        self.token = object()
        self.store["held"][self.name] = self.token
        self.store["acquired"] += 1
        return True

    async def reacquire(self):
        self.store["renewed"] += 1

    async def release(self):
        if self.store["held"].get(self.name) is self.token:
            del self.store["held"][self.name]
            self.store["released"] += 1


class _FakeRedis:
    def __init__(self, store):
        self.store = store

    def lock(self, name, timeout=None, blocking=True):
        assert blocking is False, "a second consolidation must not queue"
        return _FakeLock(self.store, name, timeout)

    async def aclose(self):
        pass


@pytest.fixture
def lease(monkeypatch):
    store = {"held": {}, "acquired": 0, "released": 0, "renewed": 0}
    monkeypatch.setattr(
        isolated.Redis, "from_url", classmethod(lambda cls, *a, **k: _FakeRedis(store))
    )
    return store


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """Point the parent at a stand-in child script written by the test."""

    def write(body):
        path = tmp_path / "runner.py"
        path.write_text(textwrap.dedent(body))
        monkeypatch.setattr(isolated, "RUNNER", str(path))
        return path

    return write


class TestChildArgv:
    def test_default_run_passes_no_type_nor_days(self):
        argv = isolated._child_argv(None, None, "r1")
        assert argv[:2] == [sys.executable, isolated.RUNNER]
        assert "--item-type" not in argv and "--days" not in argv

    def test_type_and_days_are_passed(self):
        argv = isolated._child_argv("desktops", 7, "r1")
        assert argv[argv.index("--item-type") + 1] == "desktops"
        assert argv[argv.index("--days") + 1] == "7"


class TestOutcomes:
    @pytest.mark.asyncio
    async def test_success_returns_the_child_summary_and_releases(self, lease, runner):
        runner(
            """
            import json, os, sys
            print(json.dumps({"ok": True, "inserted": 5, "pid": os.getpid()}))
            """
        )
        summary = await isolated.consolidate_isolated()
        assert summary["ok"] is True and summary["inserted"] == 5
        # it really ran in another process
        assert summary["pid"] != os.getpid()
        assert lease["held"] == {} and lease["released"] == 1

    @pytest.mark.asyncio
    async def test_rejection_is_reraised_with_the_same_error(self, lease, runner):
        runner(
            """
            import json, sys
            print(json.dumps({"ok": False, "error": "bad_request",
                              "description": "Item type x not valid"}))
            sys.exit(3)
            """
        )
        with pytest.raises(Error) as raised:
            await isolated.consolidate_isolated("x", 1)
        assert raised.value.status_code == 400
        assert "Item type x not valid" in raised.value.error["description"]
        assert lease["held"] == {}

    @pytest.mark.asyncio
    async def test_crash_is_a_failure_and_releases(self, lease, runner):
        runner(
            """
            import json, sys
            print(json.dumps({"ok": False, "exception": "KeyError", "message": "'id'"}))
            sys.exit(1)
            """
        )
        with pytest.raises(isolated.ConsolidationFailed, match="KeyError"):
            await isolated.consolidate_isolated()
        assert lease["held"] == {}

    @pytest.mark.asyncio
    async def test_killed_child_is_a_failure_and_releases(self, lease, runner):
        runner(
            """
            import os, signal
            os.kill(os.getpid(), signal.SIGKILL)
            """
        )
        with pytest.raises(isolated.ConsolidationFailed, match="signal 9"):
            await isolated.consolidate_isolated()
        assert lease["held"] == {}


class TestLease:
    @pytest.mark.asyncio
    async def test_second_run_while_one_holds_the_lease_is_409(self, lease, runner):
        runner("print('{\"ok\": true}')\n")
        lease["held"][isolated.LOCK_KEY] = object()  # another worker/node runs one
        with pytest.raises(Error) as raised:
            await isolated.consolidate_isolated()
        assert raised.value.status_code == 409
        assert raised.value.error["description_code"] == "usage_consolidation_running"
        # the other run's lease is left alone
        assert isolated.LOCK_KEY in lease["held"]

    @pytest.mark.asyncio
    async def test_redis_down_refuses_to_run_unguarded(self, lease, runner, tmp_path):
        marker = tmp_path / "ran"
        runner(f"open({str(marker)!r}, 'w').write('x')\n")
        lease["down"] = True
        with pytest.raises(Error) as raised:
            await isolated.consolidate_isolated()
        assert raised.value.status_code == 500
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_lease_is_renewed_while_the_child_runs(
        self, lease, runner, monkeypatch
    ):
        monkeypatch.setattr(isolated, "LEASE_RENEW", 0.05)
        runner(
            """
            import json, time
            time.sleep(0.4)
            print(json.dumps({"ok": True}))
            """
        )
        await isolated.consolidate_isolated()
        assert lease["renewed"] >= 2
        assert lease["held"] == {}


class TestTimeout:
    @pytest.mark.asyncio
    async def test_child_past_the_timeout_is_killed(
        self, lease, runner, monkeypatch, tmp_path
    ):
        pidfile = tmp_path / "pid"
        runner(
            f"""
            import os, time
            open({str(pidfile)!r}, "w").write(str(os.getpid()))
            time.sleep(60)
            """
        )
        monkeypatch.setenv("USAGE_CONSOLIDATION_TIMEOUT", "1")
        with pytest.raises(Error) as raised:
            await isolated.consolidate_isolated()
        assert raised.value.status_code == 504
        pid = int(pidfile.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert lease["held"] == {}

    def test_timeout_default_and_bad_values(self, monkeypatch):
        monkeypatch.delenv("USAGE_CONSOLIDATION_TIMEOUT", raising=False)
        assert isolated.consolidation_timeout() == isolated.DEFAULT_TIMEOUT
        monkeypatch.setenv("USAGE_CONSOLIDATION_TIMEOUT", "nope")
        assert isolated.consolidation_timeout() == isolated.DEFAULT_TIMEOUT
        monkeypatch.setenv("USAGE_CONSOLIDATION_TIMEOUT", "120")
        assert isolated.consolidation_timeout() == 120


def _run_real_runner(*args):
    return subprocess.run(
        [sys.executable, isolated.RUNNER, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestRealRunner:
    def test_bad_item_type_exits_rejected_with_the_service_error(self):
        # Refused before any database access, so the real child runs end to end.
        done = _run_real_runner("--item-type", "nope", "--days", "1")
        assert done.returncode == 3, done.stderr
        summary = json.loads(done.stdout.strip().splitlines()[-1])
        assert summary["ok"] is False
        assert summary["error"] == "bad_request"
        assert "nope" in summary["description"]

    def test_child_does_not_build_the_api_application(self):
        probe = textwrap.dedent(
            f"""
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location("runner", {isolated.RUNNER!r})
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            runner._bootstrap()
            import api.services.admin.usage  # noqa
            print(hasattr(sys.modules["api"], "app"), "api.routes" in sys.modules)
            """
        )
        done = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
        )
        assert done.returncode == 0, done.stderr
        assert done.stdout.split() == ["False", "False"]

    @pytest.mark.parametrize(
        "argv,expected",
        [
            ([], ()),
            (["--item-type", "desktops"], ("desktops", 29)),
            (["--item-type", "users", "--days", "7"], ("users", 7)),
        ],
    )
    def test_runner_calls_the_service_like_the_routes_did(
        self, monkeypatch, capsys, argv, expected
    ):
        from api.services.admin.usage import AdminUsageService
        from api.services.usage import run_consolidation

        called = {}
        monkeypatch.setattr(
            AdminUsageService,
            "consolidate_consumptions",
            staticmethod(lambda *a: called.update(args=a)),
        )
        assert run_consolidation.main(argv) == run_consolidation.EXIT_OK
        assert called["args"] == expected
        summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert summary["ok"] is True
        assert summary["max_rss_mib"] > 0
