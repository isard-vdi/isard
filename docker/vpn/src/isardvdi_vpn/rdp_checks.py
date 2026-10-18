# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tell, per running desktop with an RDP viewer, whether its RDP service answers and takes its credentials."""
import hashlib
import heapq
import json
import logging as log
import os
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from isardvdi_common.helpers.viewers import has_rdp_viewer

RDP_STATE = "/api/v4/admin/item/hypervisor/vm/rdp_state"
LEASES = "/var/lib/misc/vlan-wg.leases"
HELPER = os.environ.get("RDP_AUTH_CHECK", "/usr/local/bin/rdp-auth-check")
WORKERS = int(os.environ.get("RDP_CHECK_WORKERS", "16"))
PROBE_TIMEOUT = 3.0
AUTH_TIMEOUT_MS = 8000
BACKOFF = (2, 4, 8, 16, 30)
REFUSED_RETRY = 30
# Failed credential-check *runs* (not refusals) before settling to open "unverified".
VERIFY_ATTEMPTS = 3

# TPKT + X.224 Connection Request + RDP_NEG_REQ asking for TLS, CredSSP and CredSSP with Early User Auth
NEG_REQUEST = bytes.fromhex("030000130ee00000000000010008000b000000")
PROTOCOLS = {0: "rdp", 1: "tls", 2: "nla", 8: "nla"}
NEG_FAILURES = {
    1: "tls_required",
    2: "tls_not_allowed",
    3: "certificate_missing",
    4: "inconsistent_flags",
    5: "nla_required",
    6: "certificate_not_allowed",
}


def credentials(guest_properties):
    creds = (guest_properties or {}).get("credentials") or {}
    return creds.get("username") or "", creds.get("password") or ""


def wireguard_mac(domain):
    interfaces = ((domain.get("create_dict") or {}).get("hardware") or {}).get(
        "interfaces"
    ) or []
    mac = next((i.get("mac") for i in interfaces if i.get("id") == "wireguard"), None)
    return mac.lower() if mac else None


def target(domain):
    """(ip, fingerprint) of a desktop that should be checked, or None."""
    if not domain or domain.get("status") != "Started":
        return None
    ip = (domain.get("viewer") or {}).get("guest_ip")
    gp = domain.get("guest_properties")
    if not ip or not has_rdp_viewer((gp or {}).get("viewers")):
        return None
    user, password = credentials(gp)
    fingerprint = hashlib.sha256(
        f"{ip}\0{wireguard_mac(domain)}\0{user}\0{password}".encode()
    ).hexdigest()
    return ip, fingerprint


def leased_ip(mac):
    """The address dnsmasq holds for this mac right now, or None."""
    if not mac:
        return None
    try:
        with open(LEASES) as leases:
            for line in leases:
                fields = line.split()
                if len(fields) >= 3 and fields[1].lower() == mac:
                    return fields[2]
    except OSError:
        pass
    return None


def probe(ip, port=3389, timeout=PROBE_TIMEOUT):
    """X.224 negotiation only: ("waiting", reason) | ("refused", reason) | ("answers", protocol)."""
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(NEG_REQUEST)
            data = b""
            while len(data) < 19:
                chunk = sock.recv(19 - len(data))
                if not chunk:
                    break
                data += chunk
    except ConnectionRefusedError:
        return "waiting", "port_closed"
    except OSError:
        return "waiting", "unreachable"
    if len(data) < 11 or data[0] != 3 or data[5] != 0xD0:
        return "waiting", "not_rdp"
    if len(data) < 19:
        return "answers", "rdp"
    kind, value = data[11], int.from_bytes(data[15:19], "little")
    if kind == 2:
        return "answers", PROTOCOLS.get(value, "rdp")
    if kind == 3:
        return "refused", NEG_FAILURES.get(value, f"negotiation_failure_{value}")
    return "waiting", "not_rdp"


def authenticate(ip, user, password, port=3389):
    """NLA only, disconnecting before a session exists. Returns the helper's verdict dict."""
    try:
        out = subprocess.run(
            [HELPER, ip, str(port), str(AUTH_TIMEOUT_MS)],
            input=f"{user}\n{password}\n\n",
            capture_output=True,
            text=True,
            timeout=AUTH_TIMEOUT_MS / 1000 + 5,
        )
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as error:
        # only the type: the exception may carry the helper's input
        log.warning("rdp auth check of %s failed to run: %s", ip, type(error).__name__)
        return {"result": "unreachable", "name": "helper_failed"}


def verdict(
    ip,
    user,
    password,
    probe=probe,
    authenticate=authenticate,
    still_current=lambda: True,
    on_verifying=None,
):
    """One check: (state, protocol, reason, retry_in) with retry_in None for a settled state.

    ``still_current`` is asked right before the credentials leave: if the address no longer belongs to
    this desktop they are not sent. ``on_verifying`` is called once the guest offers NLA and the
    credential check is about to run, so the caller can surface the "verifying" step before the
    (slower) authentication attempt.
    """
    answer, detail = probe(ip)
    if answer == "waiting":
        return "waiting", None, detail, True
    if answer == "refused":
        return "refused", None, detail, REFUSED_RETRY
    protocol = detail
    if protocol != "nla" or not user:
        return "unverified", protocol, None if user else "no_credentials", None
    if not still_current():
        return "waiting", protocol, "ip_changed", True
    if on_verifying:
        on_verifying()
    result = authenticate(ip, user, password).get("result")
    if result == "ok":
        return "ready", protocol, None, None
    if result in ("auth_failed", "account_blocked"):
        return "auth_failed", protocol, result, None
    if result == "no_nla":
        return "unverified", protocol, None, None
    if result == "security_refused":
        return "refused", protocol, result, REFUSED_RETRY
    # Check could not run (helper error, guest briefly unreachable): stay "verifying" and retry.
    return "verifying", protocol, None, True


def post_rdp_state(domain_id, ip, state):
    from isardvdi_apiv4_client_auth import build_client

    with build_client("isard-vpn", role="hypervisor") as client:
        return (
            client.get_httpx_client()
            .post(RDP_STATE, json={"domain_id": domain_id, "ip": ip, **state})
            .status_code
        )


class RdpChecks:
    def __init__(self, check=verdict, report=post_rdp_state, workers=WORKERS):
        self._check = check
        self._report = report
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._desktops = {}
        self._queue = []
        self._pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="rdp_check"
        )

    def observe(self, domain):
        """Feed a domain row (from the changefeed or the initial load)."""
        domain_id = (domain or {}).get("id")
        if not domain_id:
            return
        wanted = target(domain)
        with self._lock:
            known = self._desktops.get(domain_id)
            if wanted is None:
                self._desktops.pop(domain_id, None)
                return
            if known and known["fingerprint"] == wanted[1]:
                return
            user, password = credentials(domain.get("guest_properties"))
            self._desktops[domain_id] = {
                "ip": wanted[0],
                "mac": wireguard_mac(domain),
                "fingerprint": wanted[1],
                "user": user,
                "password": password,
                "attempt": 0,
                "verify_attempts": 0,
                "reported": None,
            }
            self._schedule(domain_id, 0)

    def _still_current(self, domain_id, fingerprint):
        with self._lock:
            entry = self._desktops.get(domain_id)
            if not entry or entry["fingerprint"] != fingerprint:
                return False
            ip, mac = entry["ip"], entry["mac"]
        return leased_ip(mac) == ip

    def forget(self, domain_id):
        with self._lock:
            self._desktops.pop(domain_id, None)

    def _schedule(self, domain_id, delay):
        heapq.heappush(self._queue, (time.monotonic() + delay, domain_id))
        self._wake.notify()

    def _report_state(self, domain_id, ip, fingerprint, report):
        """Post one state for a still-current desktop, deduplicating repeats.

        Drops the desktop on 404 (no longer running with that IP) and reschedules
        a retry if the post itself fails or is rejected.
        """
        with self._lock:
            entry = self._desktops.get(domain_id)
            if not entry or entry["fingerprint"] != fingerprint:
                return
            if entry["reported"] == report:
                return
        try:
            status = self._report(domain_id, ip, report)
        except Exception as error:
            log.warning("rdp state of %s not reported: %s", domain_id, error)
            with self._lock:
                self._schedule(domain_id, BACKOFF[-1])
            return
        with self._lock:
            entry = self._desktops.get(domain_id)
            if status == 404:
                self._desktops.pop(domain_id, None)
            elif entry and status < 300:
                entry["reported"] = report
            elif entry:
                self._schedule(domain_id, BACKOFF[-1])

    def _run_one(self, domain_id):
        with self._lock:
            entry = self._desktops.get(domain_id)
            if not entry:
                return
            ip, fingerprint = entry["ip"], entry["fingerprint"]
            user, password = entry["user"], entry["password"]

        # Surface "verifying" before the (slower) credential check, so the user
        # sees the credentials step rather than staying on "waiting".
        def on_verifying():
            self._report_state(
                domain_id,
                ip,
                fingerprint,
                {"state": "verifying", "protocol": "nla", "reason": None},
            )

        state, protocol, reason, retry = self._check(
            ip,
            user,
            password,
            still_current=lambda: self._still_current(domain_id, fingerprint),
            on_verifying=on_verifying,
        )
        with self._lock:
            entry = self._desktops.get(domain_id)
            if not entry or entry["fingerprint"] != fingerprint:
                return
            # A check that never runs must not block forever: open "unverified" after the bound.
            if state == "verifying" and retry:
                entry["verify_attempts"] += 1
                if entry["verify_attempts"] > VERIFY_ATTEMPTS:
                    state, reason, retry = "unverified", "unreachable", None
            if retry is True:
                delay = BACKOFF[min(entry["attempt"], len(BACKOFF) - 1)]
                entry["attempt"] += 1
                self._schedule(domain_id, delay)
            elif retry:
                self._schedule(domain_id, retry)
        self._report_state(
            domain_id,
            ip,
            fingerprint,
            {"state": state, "protocol": protocol, "reason": reason},
        )

    def _loop(self):
        while True:
            with self._lock:
                while not self._queue or self._queue[0][0] > time.monotonic():
                    timeout = (
                        self._queue[0][0] - time.monotonic() if self._queue else None
                    )
                    self._wake.wait(timeout)
                _, domain_id = heapq.heappop(self._queue)
                if domain_id not in self._desktops:
                    continue
            self._pool.submit(self._safe_run, domain_id)

    def _safe_run(self, domain_id):
        try:
            self._run_one(domain_id)
        except Exception:
            log.exception("rdp check of %s", domain_id)

    def start(self):
        threading.Thread(target=self._loop, name="rdp_checks", daemon=True).start()
        return self


def load_started(conn_factory):
    """Started desktops with a guest IP, plucked to what the checks need."""
    from rethinkdb import r

    with conn_factory() as conn:
        return list(
            r.table("domains")
            .get_all("Started", index="status")
            .has_fields({"viewer": "guest_ip"})
            .pluck(
                "id",
                "status",
                {"viewer": ["guest_ip"]},
                {"guest_properties": ["viewers", "credentials"]},
                {"create_dict": {"hardware": {"interfaces": ["id", "mac"]}}},
            )
            .run(conn)
        )
