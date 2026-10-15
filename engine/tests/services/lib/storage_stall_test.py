"""Storage verdicts, health reports and the shared-storage stall condition."""

import os
import stat
import subprocess
import time

import pytest

from engine.services.lib import storage_stall as mod


class TestProbeCommand:
    """The probe as the hypervisor's shell runs it, with stand-ins for the
    tools that would touch a real mount."""

    def _run(self, tmp_path, mounts, stat_body, timeout_body=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_mounts = tmp_path / "mounts"
        fake_mounts.write_text(
            "".join(f"server:{m} {m} nfs4 rw 0 0\n" for m in mounts)
            + "/dev/sda1 / ext4 rw 0 0\n"
        )
        for name, body in (("stat", stat_body), ("timeout", timeout_body)):
            if body is None:
                continue
            path = bin_dir / name
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        cmd = mod.STORAGE_PROBE_CMD.replace("/proc/mounts", str(fake_mounts))
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
        started = time.monotonic()
        # capture_output waits for EOF: a child left holding stdout would hang
        out = subprocess.run(
            ["sh", "-c", cmd], capture_output=True, env=env, timeout=20
        ).stdout
        return mod.parse_probe_output(out), time.monotonic() - started

    def test_healthy_mounts_answer_at_once(self, tmp_path):
        hung, took = self._run(tmp_path, ["/isard/groups", "/isard/media"], "exit 0")
        assert hung == []
        assert took < 2

    def test_a_hung_mount_is_named_after_the_timeout(self, tmp_path):
        hung, took = self._run(
            tmp_path,
            ["/isard/groups", "/isard/media"],
            'case "$2" in /isard/groups) sleep 60 ;; esac; exit 0',
        )
        assert hung == ["/isard/groups"]
        assert took < mod.PROBE_TIMEOUT_S + 2

    def test_a_child_that_cannot_be_killed_does_not_hold_the_probe(self, tmp_path):
        # stands for a stat in uninterruptible sleep: timeout never returns
        hung, took = self._run(
            tmp_path,
            ["/isard/groups", "/isard/templates"],
            "exit 0",
            # argv: -s KILL <seconds> stat -f <mount>
            timeout_body='case "$6" in /isard/templates) sleep 60 ;; esac; '
            'shift 3; exec "$@"',
        )
        assert hung == ["/isard/templates"]
        assert took < mod.PROBE_TIMEOUT_S + 2

    def test_mounts_outside_isard_are_not_probed(self, tmp_path):
        hung, _ = self._run(tmp_path, ["/srv/other"], "sleep 60")
        assert hung == []


class TestParseProbeOutput:
    def test_only_paths_are_kept(self):
        assert mod.parse_probe_output(b"/isard/b\nnoise\n/isard/a\n/isard/b\n") == [
            "/isard/a",
            "/isard/b",
        ]

    def test_garbage_is_no_mount(self):
        assert mod.parse_probe_output(None) == []


class TestHealthVerdict:
    NOW = 1000.0

    def test_never_reported_is_not_judged(self):
        assert mod.health_verdict(None, self.NOW) == (None, [])
        assert mod.health_verdict({"hung_mounts": ["/isard/x"]}, self.NOW) == (
            None,
            [],
        )

    def test_fresh_and_clean(self):
        assert mod.health_verdict({"received_at": self.NOW - 5}, self.NOW) == (
            None,
            [],
        )

    def test_a_fresh_report_with_a_hung_mount(self):
        reason, hung = mod.health_verdict(
            {"received_at": self.NOW - 5, "hung_mounts": ["/isard/groups"]}, self.NOW
        )
        assert hung == ["/isard/groups"]
        assert reason.startswith("health: storage")

    def test_a_stale_report_degrades_and_names_no_mount(self):
        reason, hung = mod.health_verdict(
            {"received_at": self.NOW - 31, "hung_mounts": ["/isard/groups"]},
            self.NOW,
        )
        assert hung == []
        assert reason == "health: no report for 31s"

    def test_thirty_seconds_is_still_fresh(self):
        assert mod.health_verdict({"received_at": self.NOW - 30}, self.NOW)[0] is None


class TestAssessHypervisors:
    def test_each_cause_is_named(self):
        now = 1000.0
        causes, hung = mod.assess_hypervisors(
            ["probe-hung", "probe-failed", "health-stale", "ok"],
            {
                "probe-hung": {"hung": ["/isard/groups"], "error": None},
                "probe-failed": {"hung": [], "error": "ssh timed out"},
                "health-stale": {"hung": [], "error": None},
                "ok": {"hung": [], "error": None},
            },
            {"health-stale": {"received_at": now - 60}, "ok": {"received_at": now}},
            now,
        )
        assert causes["probe-hung"] == "storage: not responding: /isard/groups"
        assert causes["probe-failed"] == "storage: probe failed: ssh timed out"
        assert causes["health-stale"].startswith("health: no report")
        assert "ok" not in causes
        assert hung == {"probe-hung": ["/isard/groups"]}

    def test_probe_and_health_mounts_are_merged(self):
        now = 1000.0
        _, hung = mod.assess_hypervisors(
            ["h1"],
            {"h1": {"hung": ["/isard/a"], "error": None}},
            {"h1": {"received_at": now, "hung_mounts": ["/isard/b"]}},
            now,
        )
        assert hung == {"h1": ["/isard/a", "/isard/b"]}


class TestSharedMounts:
    @pytest.mark.parametrize(
        "online,hung,shared",
        [
            # the only hypervisor: the storage is all there is
            (["h1"], {"h1": ["/isard/g"]}, {"/isard/g"}),
            # two: both must agree
            (["h1", "h2"], {"h1": ["/isard/g"]}, set()),
            (["h1", "h2"], {"h1": ["/isard/g"], "h2": ["/isard/g"]}, {"/isard/g"}),
            # three: two is half or more
            (
                ["h1", "h2", "h3"],
                {"h1": ["/isard/g"], "h2": ["/isard/g"]},
                {"/isard/g"},
            ),
            # eight: three is not half, four is
            (
                [f"h{i}" for i in range(8)],
                {f"h{i}": ["/isard/g"] for i in range(3)},
                set(),
            ),
            (
                [f"h{i}" for i in range(8)],
                {f"h{i}": ["/isard/g"] for i in range(4)},
                {"/isard/g"},
            ),
            # different mounts do not add up
            (["h1", "h2"], {"h1": ["/isard/a"], "h2": ["/isard/b"]}, set()),
            # a hypervisor that is not online does not count
            (["h1", "h2"], {"h1": ["/isard/g"], "off": ["/isard/g"]}, set()),
        ],
    )
    def test_threshold(self, online, hung, shared):
        assert set(mod.shared_mounts(online, hung)) == shared


class TestSharedStorageStall:
    ONLINE = ["h1", "h2", "h3"]
    HUNG = {"h1": ["/isard/groups"], "h2": ["/isard/groups"]}

    def test_set_in_one_pass(self):
        stall = mod.SharedStorageStall()
        assert stall.observe(self.ONLINE, self.HUNG, 10.0) == "set"
        assert stall.state == {
            "active": True,
            "since": 10.0,
            "hypervisors": ["h1", "h2"],
            "mounts": ["/isard/groups"],
            "online": 3,
        }

    def test_unchanged_is_quiet_and_keeps_since(self):
        stall = mod.SharedStorageStall()
        stall.observe(self.ONLINE, self.HUNG, 10.0)
        assert stall.observe(self.ONLINE, self.HUNG, 20.0) is None
        assert stall.state["since"] == 10.0

    def test_spreading_is_an_update(self):
        stall = mod.SharedStorageStall()
        stall.observe(self.ONLINE, self.HUNG, 10.0)
        more = dict(self.HUNG, h3=["/isard/groups"])
        assert stall.observe(self.ONLINE, more, 20.0) == "update"
        assert stall.state["hypervisors"] == ["h1", "h2", "h3"]
        assert stall.state["since"] == 10.0

    def test_cleared_only_after_two_clean_passes(self):
        stall = mod.SharedStorageStall()
        stall.observe(self.ONLINE, self.HUNG, 10.0)
        assert stall.observe(self.ONLINE, {}, 20.0) is None
        assert stall.state["active"] is True
        assert stall.observe(self.ONLINE, {}, 30.0) == "clear"
        assert stall.state is None
        assert stall.last_cleared["active"] is False
        assert stall.last_cleared["cleared_at"] == 30.0
        assert stall.last_cleared["since"] == 10.0

    def test_a_relapse_resets_the_clean_count(self):
        stall = mod.SharedStorageStall()
        stall.observe(self.ONLINE, self.HUNG, 10.0)
        stall.observe(self.ONLINE, {}, 20.0)
        stall.observe(self.ONLINE, self.HUNG, 30.0)
        assert stall.observe(self.ONLINE, {}, 40.0) is None
        assert stall.observe(self.ONLINE, {}, 50.0) == "clear"

    def test_one_hypervisor_hung_is_not_shared(self):
        stall = mod.SharedStorageStall()
        assert stall.observe(self.ONLINE, {"h1": ["/isard/groups"]}, 10.0) is None
        assert stall.state is None

    def test_a_condition_left_by_a_previous_process_is_cleared(self):
        stall = mod.SharedStorageStall()
        stall.resume({"active": True, "since": 5.0, "hypervisors": ["h1"]})
        stall.observe(self.ONLINE, {}, 10.0)
        assert stall.observe(self.ONLINE, {}, 20.0) == "clear"

    def test_an_inactive_stored_condition_is_not_resumed(self):
        stall = mod.SharedStorageStall()
        stall.resume({"active": False, "since": 5.0})
        assert stall.state is None
