# Copyright 2026 the Isard-vdi project authors
# License: AGPLv3

"""Hypervisor storage verdicts and the install-level shared-storage stall."""

import math

PROBE_TIMEOUT_S = 3

PROBE_DEADLINE_S = PROBE_TIMEOUT_S + 5

HEALTH_STALE_S = 30

STALL_CLEAR_PASSES = 2

STALL_LOG_TOKEN = "SHARED_STORAGE_STALL"

# a stat stuck in D state can be neither waited for nor left holding the ssh channel
STORAGE_PROBE_CMD = (
    "cd / || exit 1; f=$(mktemp) || exit 1; "
    "ms=$(awk '$2 ~ \"^/isard\" {print $2}' /proc/mounts); n=0; "
    "for m in $ms; do n=$((n+1)); "
    f'(timeout -s KILL {PROBE_TIMEOUT_S} stat -f "$m" && echo "$m" >> "$f") '
    ">/dev/null 2>&1 </dev/null & done; "
    f"i=0; while [ $i -lt {PROBE_TIMEOUT_S * 10} ] && "
    '[ "$(wc -l < "$f")" -lt "$n" ]; do sleep 0.1; i=$((i+1)); done; '
    'for m in $ms; do grep -qxF "$m" "$f" || echo "$m"; done; rm -f "$f"'
)


def parse_probe_output(out):
    """The mounts the probe reported as not answering."""
    if isinstance(out, bytes):
        out = out.decode(errors="replace")
    if not isinstance(out, str):
        return []
    return sorted({line.strip() for line in out.splitlines() if line.startswith("/")})


def health_verdict(health, now, stale_after=HEALTH_STALE_S):
    """``(reason, hung_mounts)``; a hypervisor that never reported is not judged."""
    if not isinstance(health, dict):
        return None, []
    received_at = health.get("received_at")
    if not isinstance(received_at, (int, float)):
        return None, []
    age = now - received_at
    if age > stale_after:
        return f"health: no report for {int(age)}s", []
    hung = sorted(
        {m for m in health.get("hung_mounts") or [] if isinstance(m, str) and m}
    )
    if hung:
        return "health: storage not responding: " + " ".join(hung), hung
    return None, []


def assess_hypervisors(hyp_ids, probes, healths, now):
    """``(causes, hung_by_hyp)``: why each hypervisor is degraded, what hangs where."""
    causes = {}
    hung_by_hyp = {}
    for hyp_id in hyp_ids:
        reasons = []
        hung = set()
        probe = probes.get(hyp_id)
        if probe is not None:
            if probe.get("hung"):
                hung.update(probe["hung"])
                reasons.append(
                    "storage: not responding: " + " ".join(sorted(probe["hung"]))
                )
            elif probe.get("error"):
                reasons.append(f"storage: probe failed: {probe['error']}")
        reason, health_hung = health_verdict(healths.get(hyp_id), now)
        if reason:
            reasons.append(reason)
            hung.update(health_hung)
        if reasons:
            causes[hyp_id] = "; ".join(reasons)
        if hung:
            hung_by_hyp[hyp_id] = sorted(hung)
    return causes, hung_by_hyp


def shared_mounts(online, hung_by_hyp):
    """Mounts hung on half or more of the online hypervisors (at least two)."""
    online = set(online)
    if not online:
        return {}
    needed = 1 if len(online) == 1 else max(2, math.ceil(len(online) / 2))
    by_mount = {}
    for hyp_id, mounts in hung_by_hyp.items():
        if hyp_id not in online:
            continue
        for mount in mounts:
            by_mount.setdefault(mount, set()).add(hyp_id)
    return {m: hyps for m, hyps in by_mount.items() if len(hyps) >= needed}


class SharedStorageStall:
    """Set in the pass that sees it, cleared after ``clear_after`` clean passes."""

    def __init__(self, clear_after=STALL_CLEAR_PASSES):
        self.clear_after = clear_after
        self.state = None
        self.last_cleared = None
        self._clean_passes = 0

    def resume(self, state):
        if isinstance(state, dict) and state.get("active"):
            self.state = dict(state)
            self._clean_passes = 0

    def observe(self, online, hung_by_hyp, now):
        shared = shared_mounts(online, hung_by_hyp)
        if shared:
            self._clean_passes = 0
            hypervisors = sorted(set().union(*shared.values()))
            mounts = sorted(shared)
            if self.state is None:
                self.state = {
                    "active": True,
                    "since": now,
                    "hypervisors": hypervisors,
                    "mounts": mounts,
                    "online": len(set(online)),
                }
                return "set"
            if (
                self.state.get("hypervisors") != hypervisors
                or self.state.get("mounts") != mounts
            ):
                self.state.update(
                    hypervisors=hypervisors, mounts=mounts, online=len(set(online))
                )
                return "update"
            return None
        if self.state is None:
            return None
        self._clean_passes += 1
        if self._clean_passes < self.clear_after:
            return None
        self.last_cleared = dict(self.state, active=False, cleared_at=now)
        self.state = None
        self._clean_passes = 0
        return "clear"
