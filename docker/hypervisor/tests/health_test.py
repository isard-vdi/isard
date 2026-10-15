"""The hypervisor's own health report: what it measures, and that it never hangs."""

import subprocess

import pytest
from isardvdi_hypervisor import health as mod

MOUNTSTATS = "\n".join(
    [
        "device proc mounted on /proc with fstype proc",
        "device 192.0.2.1:/opt/isard/groups mounted on /isard/groups with fstype nfs4"
        " statvers=1.1",
        "\topts:\trw,vers=4.2",
        "\tage:\t100",
        "\txprt:\ttcp 875 1 1 0 0 85 85 0 85 {bklog} 2 0 0",
        "\tper-op statistics",
        "\t        NULL: 1 1 0 44 24 0 0 0 0",
        "\t        READ: {reads} {reads_trans} {timeouts} 456 12345 0 {rtt} {exe} 0",
        "\t       WRITE: 2 2 0 100 100 0 4 6 0",
        "device 192.0.2.1:/opt/isard/media mounted on /srv/media with fstype nfs4"
        " statvers=1.1",
        "\txprt:\ttcp 875 1 1 0 0 85 85 0 85 0 2 0 0",
        "\t        READ: 9 9 0 456 12345 0 5 6 0",
        "device /dev/sda1 mounted on /isard/local with fstype ext4",
        "",
    ]
)


def _stats(reads=3, reads_trans=3, timeouts=0, rtt=6, exe=9, bklog=0):
    return MOUNTSTATS.format(
        reads=reads,
        reads_trans=reads_trans,
        timeouts=timeouts,
        rtt=rtt,
        exe=exe,
        bklog=bklog,
    )


class TestMounts:
    def test_only_isard_mounts(self):
        text = (
            "srv:/g /isard/groups nfs4 rw 0 0\n"
            "srv:/m /isard/media nfs4 rw 0 0\n"
            "/dev/sda1 / ext4 rw 0 0\n"
            "srv:/x /isardish nfs4 rw 0 0\n"
        )
        assert mod.isard_mounts(text) == ["/isard/groups", "/isard/media"]


class TestMountstats:
    def test_only_isard_nfs_mounts_are_counted(self):
        stats = mod.parse_mountstats(_stats())
        assert list(stats) == ["/isard/groups"]
        assert stats["/isard/groups"]["ops"] == 1 + 3 + 2

    def test_deltas_between_two_samples(self):
        before = mod.parse_mountstats(_stats())
        after = mod.parse_mountstats(
            _stats(reads=13, reads_trans=16, timeouts=2, rtt=106, exe=309, bklog=7)
        )
        delta = mod.mountstats_delta(before, after)["/isard/groups"]
        assert delta == {
            "ops": 10,
            "retrans": 3,
            "major_timeouts": 2,
            "avg_rtt_ms": 10.0,
            "avg_exe_ms": 30.0,
            "backlog": 7,
        }

    def test_no_traffic_has_no_averages(self):
        stats = mod.parse_mountstats(_stats())
        delta = mod.mountstats_delta(stats, stats)["/isard/groups"]
        assert delta["ops"] == 0
        assert delta["avg_rtt_ms"] is None

    def test_a_mount_seen_for_the_first_time_has_no_delta(self):
        assert mod.mountstats_delta({}, mod.parse_mountstats(_stats())) == {}


class FakeProc:
    def __init__(self, code):
        self.code = code
        self.killed = False

    def poll(self):
        return self.code

    def kill(self):
        self.killed = True


class TestMountProber:
    def _prober(self, answers, timeout=0.2):
        started = []

        def popen(args, **kwargs):
            assert kwargs["cwd"] == "/"
            assert kwargs["stdout"] is subprocess.DEVNULL
            started.append(args[-1])
            return FakeProc(answers[args[-1]])

        return mod.MountProber(timeout=timeout, popen=popen), started

    def test_a_hung_mount_is_reported_after_the_timeout(self):
        prober, _ = self._prober({"/isard/groups": None, "/isard/media": 0})
        result = prober.probe(["/isard/groups", "/isard/media"])
        assert result["/isard/groups"]["ok"] is False
        assert result["/isard/media"]["ok"] is True

    def test_a_still_stuck_probe_is_not_started_again(self):
        prober, started = self._prober({"/isard/groups": None})
        prober.probe(["/isard/groups"])
        result = prober.probe(["/isard/groups"])
        assert started == ["/isard/groups"]
        assert result["/isard/groups"] == {"ok": False, "ms": None, "stuck": True}

    def test_a_failed_stat_is_not_ok(self):
        prober, _ = self._prober({"/isard/groups": 1})
        assert prober.probe(["/isard/groups"])["/isard/groups"]["ok"] is False

    def test_real_children_never_outlive_the_timeout(self):
        prober = mod.MountProber(timeout=0.3)
        result = prober.probe(["/"])
        assert result["/"]["ok"] is True


class TestProcCounters:
    def _proc(self, tmp_path, threads):
        for pid, (comm, states) in threads.items():
            for tid, state in states.items():
                task = tmp_path / str(pid) / "task" / str(tid)
                task.mkdir(parents=True)
                (task / "stat").write_text(f"{tid} ({comm} x) {state} 1 2 3\n")
            (tmp_path / str(pid) / "comm").write_text(comm + "\n")
        (tmp_path / "loadavg").write_text("3.50 2.00 1.00 1/200 999\n")
        (tmp_path / "stat").write_text("cpu 1 2 3\nprocs_running 2\nprocs_blocked 7\n")
        return str(tmp_path)

    def test_qemu_threads_in_uninterruptible_sleep(self, tmp_path):
        root = self._proc(
            tmp_path,
            {
                10: ("qemu-system-x86", {10: "S", 11: "D", 12: "D"}),
                20: ("bash", {20: "D"}),
            },
        )
        assert mod.qemu_threads_in_d_state(root) == 2

    def test_load_and_blocked(self, tmp_path):
        root = self._proc(tmp_path, {})
        assert mod.load_and_blocked(root) == (3.5, 7)

    def test_an_unreadable_proc_is_unknown(self, tmp_path):
        assert mod.qemu_threads_in_d_state(str(tmp_path / "missing")) is None


class TestLibvirt:
    def test_a_libvirt_that_does_not_answer_is_unknown(self):
        def run(*a, **k):
            raise subprocess.TimeoutExpired("virsh", 3)

        assert mod.libvirt_response_ms(run=run) is None

    def test_a_libvirt_that_answers_is_timed(self):
        assert isinstance(mod.libvirt_response_ms(run=lambda *a, **k: None), int)


class TestReport:
    def test_hung_mounts_are_listed(self, monkeypatch):
        class Prober:
            def probe(self, mounts):
                return {
                    "/isard/groups": {"ok": False, "ms": None},
                    "/isard/media": {"ok": True, "ms": 2},
                }

        monkeypatch.setattr(mod, "read_text", lambda path: "")
        monkeypatch.setattr(mod, "libvirt_response_ms", lambda: 12)
        report = mod.HealthReporter(prober=Prober()).report()
        assert report["hung_mounts"] == ["/isard/groups"]
        assert report["libvirt_ms"] == 12
        assert report["nfs"] == {}
        assert set(report) >= {
            "timestamp",
            "mounts",
            "qemu_d_state_threads",
            "load1",
            "procs_blocked",
        }
