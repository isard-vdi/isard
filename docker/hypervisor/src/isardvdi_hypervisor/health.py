"""Report this hypervisor's storage, libvirt and load health to the API."""

import os
import subprocess
import time
import traceback

INTERVAL_S = 10
PROBE_TIMEOUT_S = 3
MOUNT_PREFIX = "/isard"


def isard_mounts(proc_mounts):
    """Mount points under /isard, from the text of /proc/mounts."""
    mounts = []
    for line in proc_mounts.splitlines():
        fields = line.split()
        if len(fields) > 1 and (
            fields[1] == MOUNT_PREFIX or fields[1].startswith(MOUNT_PREFIX + "/")
        ):
            mounts.append(fields[1])
    return sorted(set(mounts))


class MountProber:
    """``stat -f`` each mount in a child; a stuck child is never started twice."""

    def __init__(self, timeout=PROBE_TIMEOUT_S, popen=subprocess.Popen):
        self.timeout = timeout
        self.popen = popen
        self._stuck = {}

    def probe(self, mounts):
        results = {}
        running = {}
        for mount in mounts:
            stuck = self._stuck.get(mount)
            if stuck is not None:
                if stuck.poll() is None:
                    results[mount] = {"ok": False, "ms": None, "stuck": True}
                    continue
                del self._stuck[mount]
            running[mount] = (
                self.popen(
                    ["stat", "-f", mount],
                    cwd="/",
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
                time.monotonic(),
            )
        deadline = time.monotonic() + self.timeout
        while running:
            for mount, (proc, started) in list(running.items()):
                code = proc.poll()
                if code is not None:
                    results[mount] = {
                        "ok": code == 0,
                        "ms": int((time.monotonic() - started) * 1000),
                    }
                    del running[mount]
            if not running or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        for mount, (proc, _started) in running.items():
            try:
                proc.kill()
            except Exception:
                pass
            self._stuck[mount] = proc
            results[mount] = {"ok": False, "ms": None, "stuck": False}
        return results


def parse_mountstats(text):
    """Cumulative NFS client counters per mount from /proc/self/mountstats."""
    stats = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("device "):
            fields = line.split()
            current = None
            if "mounted" in fields and "fstype" in fields:
                mount = fields[fields.index("mounted") + 2]
                fstype = fields[fields.index("fstype") + 1]
                if fstype.startswith("nfs") and (
                    mount == MOUNT_PREFIX or mount.startswith(MOUNT_PREFIX + "/")
                ):
                    current = stats.setdefault(
                        mount,
                        {
                            "ops": 0,
                            "trans": 0,
                            "timeouts": 0,
                            "rtt_ms": 0,
                            "exe_ms": 0,
                            "backlog": 0,
                        },
                    )
            continue
        if current is None:
            continue
        if line.startswith("xprt:"):
            fields = line.split()
            # bklog_u is the last xprt field: index 11 on tcp, 8 on udp
            index = {"tcp": 11, "udp": 8}.get(fields[1] if len(fields) > 1 else "")
            try:
                current["backlog"] = int(fields[index])
            except (IndexError, TypeError, ValueError):
                pass
            continue
        name, _, values = line.partition(":")
        if not name.isupper() or not values:
            continue
        fields = values.split()
        if len(fields) < 8:
            continue
        try:
            ops, trans, timeouts = int(fields[0]), int(fields[1]), int(fields[2])
            rtt, exe = int(fields[6]), int(fields[7])
        except ValueError:
            continue
        current["ops"] += ops
        current["trans"] += trans
        current["timeouts"] += timeouts
        current["rtt_ms"] += rtt
        current["exe_ms"] += exe
    return stats


def mountstats_delta(previous, current):
    """What happened on each NFS mount between two samples."""
    deltas = {}
    for mount, now in current.items():
        before = previous.get(mount)
        if before is None:
            continue
        ops = now["ops"] - before["ops"]
        deltas[mount] = {
            "ops": ops,
            "retrans": max(0, (now["trans"] - before["trans"]) - ops),
            "major_timeouts": now["timeouts"] - before["timeouts"],
            "avg_rtt_ms": (
                round((now["rtt_ms"] - before["rtt_ms"]) / ops, 1) if ops > 0 else None
            ),
            "avg_exe_ms": (
                round((now["exe_ms"] - before["exe_ms"]) / ops, 1) if ops > 0 else None
            ),
            "backlog": now["backlog"] - before["backlog"],
        }
    return deltas


def qemu_threads_in_d_state(proc_root="/proc"):
    """qemu threads in uninterruptible sleep: guests blocked on their disks."""
    count = 0
    try:
        pids = [p for p in os.listdir(proc_root) if p.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(os.path.join(proc_root, pid, "comm")) as f:
                if not f.read().startswith("qemu"):
                    continue
            tasks = os.listdir(os.path.join(proc_root, pid, "task"))
        except OSError:
            continue
        for tid in tasks:
            try:
                with open(os.path.join(proc_root, pid, "task", tid, "stat")) as f:
                    stat = f.read()
            except OSError:
                continue
            # the state follows the parenthesised command, which may hold spaces
            state = stat.rpartition(")")[2].split()
            if state and state[0] == "D":
                count += 1
    return count


def libvirt_response_ms(timeout=PROBE_TIMEOUT_S, run=subprocess.run):
    started = time.monotonic()
    try:
        run(
            ["virsh", "-c", "qemu:///system", "list", "--name"],
            cwd="/",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=True,
        )
    except Exception:
        return None
    return int((time.monotonic() - started) * 1000)


def load_and_blocked(proc_root="/proc"):
    load1 = blocked = None
    try:
        with open(os.path.join(proc_root, "loadavg")) as f:
            load1 = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(os.path.join(proc_root, "stat")) as f:
            for line in f:
                if line.startswith("procs_blocked "):
                    blocked = int(line.split()[1])
                    break
    except (OSError, ValueError):
        pass
    return load1, blocked


def read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


class HealthReporter:
    def __init__(self, prober=None):
        self.prober = prober or MountProber()
        self._mountstats = None

    def report(self):
        mounts = isard_mounts(read_text("/proc/mounts"))
        probes = self.prober.probe(mounts)
        mountstats = parse_mountstats(read_text("/proc/self/mountstats"))
        nfs = (
            mountstats_delta(self._mountstats, mountstats)
            if self._mountstats is not None
            else {}
        )
        self._mountstats = mountstats
        load1, blocked = load_and_blocked()
        return {
            "timestamp": int(time.time()),
            "interval_s": INTERVAL_S,
            "mounts": probes,
            "hung_mounts": sorted(m for m, p in probes.items() if not p["ok"]),
            "nfs": nfs,
            "qemu_d_state_threads": qemu_threads_in_d_state(),
            "libvirt_ms": libvirt_response_ms(),
            "load1": load1,
            "procs_blocked": blocked,
        }


def send(health):
    from isardvdi_apiv4_client.api.role_admin import admin_hypervisor_health
    from isardvdi_apiv4_client.models import (
        AdminHypervisorHealthRequest,
        AdminHypervisorHealthRequestHealth,
    )
    from isardvdi_apiv4_client_auth import build_client, raise_for_status

    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    with build_client("isard-hypervisor", role="hypervisor") as client:
        resp = admin_hypervisor_health.sync_detailed(
            hyper_id=hyper_id,
            client=client,
            body=AdminHypervisorHealthRequest(
                health=AdminHypervisorHealthRequestHealth.from_dict(health)
            ),
        )
        raise_for_status(resp)


def main():
    os.chdir("/")
    reporter = HealthReporter()
    while True:
        started = time.monotonic()
        try:
            send(reporter.report())
        except Exception:
            traceback.print_exc()
        time.sleep(max(1.0, INTERVAL_S - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
