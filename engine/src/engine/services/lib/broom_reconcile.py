# Copyright 2026 the Isard-vdi project authors
# License: AGPLv3

"""Which domain rows the broom settles from fresh listings of every online hypervisor."""

ABSENT_PASSES_TO_STOP = 2

IDLE_PAUSED_VCPU_S = 1.0
IDLE_PAUSED_AFTER_S = 600

STATUSES_SETTLED_WHEN_ABSENT = ("Unknown", "Started", "Paused")

# their libvirt domain belongs to a flow that is still running
STATUSES_NEVER_REAPED = (
    "CreatingDomain",
    "CreatingAndStarting",
    "CreatingDiskFromScratch",
    "StartingDomainDisposable",
    "StartingPaused",
    "Starting",
    "Stopping",
    "Shutting-down",
    "Resetting",
    "Deleting",
    "ForceDeleting",
)


def vcpu_seconds(dom):
    """CPU time the guest's vCPUs have run; the emulator keeps adding to the domain total while paused."""
    return sum(vcpu[2] for vcpu in dom.vcpus()[0]) / 1e9


def _hyp_of(row):
    hyp_id = row.get("hyp_started")
    return hyp_id if hyp_id and not isinstance(hyp_id, bool) else None


class AbsenceTracker:
    """Rows no libvirt runs, confirmed over consecutive passes in which every online hypervisor answered."""

    def __init__(self, passes=ABSENT_PASSES_TO_STOP):
        self.passes = passes
        self._seen = {}

    def absent(self, rows, online, listings, is_held):
        if not online or not set(online) <= set(listings):
            self._seen = {}
            return []
        listed = set()
        for states in listings.values():
            listed.update(states)
        seen = {}
        due = []
        for row in rows:
            domain_id = row["id"]
            if row.get("status") not in STATUSES_SETTLED_WHEN_ABSENT:
                continue
            if domain_id in listed or is_held(domain_id):
                continue
            hyp_id = _hyp_of(row)
            if hyp_id is not None and hyp_id not in listings:
                continue
            key = (row["status"], hyp_id)
            previous = self._seen.get(domain_id)
            count = previous[1] + 1 if previous and previous[0] == key else 1
            seen[domain_id] = (key, count)
            if count >= self.passes:
                due.append(row)
        self._seen = seen
        return due


class IdlePausedTracker:
    """Domains left paused at start: their vCPUs never ran, for long enough."""

    def __init__(self, after_s=IDLE_PAUSED_AFTER_S, vcpu_s=IDLE_PAUSED_VCPU_S):
        self.after_s = after_s
        self.vcpu_s = vcpu_s
        self._since = {}

    @staticmethod
    def candidates(listings, vcpu_s=IDLE_PAUSED_VCPU_S):
        return {
            domain_id
            for states in listings.values()
            for domain_id, state in states.items()
            if state.get("status") == "Paused"
            and state.get("vcpu_time") is not None
            and state["vcpu_time"] < vcpu_s
        }

    def due(self, listings, statuses, is_held, now):
        """``[(hyp_id, domain_id, status, vcpu_time)]`` to destroy."""
        since = {}
        due = []
        for hyp_id, states in listings.items():
            for domain_id, state in states.items():
                vcpu_time = state.get("vcpu_time")
                if state.get("status") != "Paused" or vcpu_time is None:
                    continue
                if vcpu_time >= self.vcpu_s:
                    continue
                status = statuses.get(domain_id)
                if status is None or status in STATUSES_NEVER_REAPED:
                    continue
                if is_held(domain_id):
                    continue
                key = (hyp_id, round(vcpu_time, 3), status)
                previous = self._since.get(domain_id)
                first = previous[1] if previous and previous[0] == key else now
                since[domain_id] = (key, first)
                if now - first >= self.after_s:
                    due.append((hyp_id, domain_id, status, vcpu_time))
        self._since = since
        return due
