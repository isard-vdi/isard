# SPDX-License-Identifier: AGPL-3.0-or-later
"""RDP readiness: which desktops are checked, how a guest answer is read, and what gets reported."""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading

import pytest
from isardvdi_vpn import rdp_checks

MAC = "52:54:00:aa:bb:cc"
SECRET = "s3cret-Pa55"


def _domain(
    status="Started", ip="192.0.2.5", viewers=None, user="isard", password="pw"
):
    return {
        "id": "d1",
        "status": status,
        "create_dict": {"hardware": {"interfaces": [{"id": "wireguard", "mac": MAC}]}},
        "viewer": {"guest_ip": ip} if ip else {},
        "guest_properties": {
            "viewers": (
                {"browser_rdp": {"options": None}} if viewers is None else viewers
            ),
            "credentials": {"username": user, "password": password},
        },
    }


def test_only_started_desktops_with_an_ip_and_an_rdp_viewer_are_checked():
    assert rdp_checks.target(_domain())[0] == "192.0.2.5"
    assert rdp_checks.target(_domain(status="Stopped")) is None
    assert rdp_checks.target(_domain(ip=None)) is None
    assert (
        rdp_checks.target(_domain(viewers={"browser_vnc": {"options": None}})) is None
    )
    assert rdp_checks.target(_domain(viewers={"browser_rdp": None})) is None


def test_new_credentials_make_a_new_check():
    assert (
        rdp_checks.target(_domain())[1]
        != rdp_checks.target(_domain(password="other"))[1]
    )
    assert (
        rdp_checks.target(_domain())[1] != rdp_checks.target(_domain(ip="192.0.2.6"))[1]
    )


def _server(reply):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        conn.recv(64)
        if reply:
            conn.sendall(reply)
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1]


def _confirm(kind, value):
    return (
        bytes.fromhex("030000130ed00000123400")
        + bytes([kind, 0, 8, 0])
        + value.to_bytes(4, "little")
    )


@pytest.mark.parametrize(
    "reply,expected",
    [
        (_confirm(2, 2), ("answers", "nla")),
        (_confirm(2, 8), ("answers", "nla")),
        (_confirm(2, 1), ("answers", "tls")),
        (_confirm(3, 5), ("refused", "nla_required")),
        (_confirm(3, 2), ("refused", "tls_not_allowed")),
        (b"HTTP/1.1 400 Bad Request\r\n\r\n", ("waiting", "not_rdp")),
        (b"", ("waiting", "not_rdp")),
    ],
)
def test_the_negotiation_answer_is_classified(reply, expected):
    assert rdp_checks.probe("127.0.0.1", _server(reply)) == expected


def test_a_closed_port_is_waiting_not_refused():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert rdp_checks.probe("127.0.0.1", port) == ("waiting", "port_closed")


def _verdict(answer, auth=None, user="isard"):
    calls = []

    def authenticate(ip, u, p):
        calls.append((ip, u, p))
        return auth

    result = rdp_checks.verdict(
        "192.0.2.5", user, "pw", probe=lambda ip: answer, authenticate=authenticate
    )
    return result, calls


def test_nla_guest_with_good_credentials_is_ready():
    result, calls = _verdict(("answers", "nla"), {"result": "ok"})
    assert result == ("ready", "nla", None, None)
    assert calls == [("192.0.2.5", "isard", "pw")]


def test_rejected_credentials_are_settled_and_not_retried():
    result, _ = _verdict(
        ("answers", "nla"),
        {"result": "auth_failed", "name": "ERRCONNECT_LOGON_FAILURE"},
    )
    assert result == ("auth_failed", "nla", "auth_failed", None)


def test_a_guest_without_nla_cannot_have_its_credentials_verified():
    result, calls = _verdict(("answers", "tls"))
    assert result == ("unverified", "tls", None, None)
    assert calls == []


def test_without_stored_credentials_nothing_is_tried():
    result, calls = _verdict(("answers", "nla"), user="")
    assert result == ("unverified", "nla", "no_credentials", None)
    assert calls == []


def test_waiting_and_refused_are_retried():
    assert _verdict(("waiting", "port_closed"))[0] == (
        "waiting",
        None,
        "port_closed",
        True,
    )
    assert _verdict(("refused", "nla_required"))[0] == (
        "refused",
        None,
        "nla_required",
        rdp_checks.REFUSED_RETRY,
    )


def _checks(results, statuses=None):
    reports = []
    results = list(results)
    statuses = list(statuses or [])

    def check(ip, user, password, still_current=None):
        return results.pop(0)

    def report(domain_id, ip, state):
        reports.append((domain_id, ip, state))
        return statuses.pop(0) if statuses else 204

    checks = rdp_checks.RdpChecks(check=check, report=report, workers=1)
    return checks, reports


def test_a_state_is_reported_once_until_it_changes():
    checks, reports = _checks(
        [
            ("waiting", None, "port_closed", True),
            ("waiting", None, "port_closed", True),
            ("ready", "nla", None, None),
        ]
    )
    checks.observe(_domain())
    for _ in range(3):
        checks._run_one("d1")
    assert [r[2]["state"] for r in reports] == ["waiting", "ready"]


def test_the_desktop_reporting_its_own_state_back_does_not_trigger_a_check():
    checks, _ = _checks([])
    checks.observe(_domain())
    queued = len(checks._queue)
    echoed = _domain()
    echoed["viewer"]["rdp"] = {"state": "ready"}
    checks.observe(echoed)
    assert len(checks._queue) == queued


def test_a_stopped_desktop_is_forgotten():
    checks, reports = _checks([("ready", "nla", None, None)])
    checks.observe(_domain())
    checks.observe(_domain(status="Stopped"))
    checks._run_one("d1")
    assert reports == []


def test_a_desktop_the_api_no_longer_finds_is_forgotten():
    checks, _ = _checks([("ready", "nla", None, None)], statuses=[404])
    checks.observe(_domain())
    checks._run_one("d1")
    assert "d1" not in checks._desktops


def test_the_password_goes_by_stdin_and_never_in_the_command_line(monkeypatch):
    seen = {}

    def run(argv, **kwargs):
        seen["argv"], seen["input"] = argv, kwargs.get("input", "")
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps({"result": "ok"}), stderr=""
        )

    monkeypatch.setattr(rdp_checks.subprocess, "run", run)
    assert rdp_checks.authenticate("192.0.2.5", "isard", SECRET) == {"result": "ok"}
    assert not any(SECRET in str(arg) for arg in seen["argv"])
    assert SECRET in seen["input"]


def test_the_password_never_reaches_the_logs(monkeypatch, caplog):
    def run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1, output=kwargs.get("input"))

    monkeypatch.setattr(rdp_checks.subprocess, "run", run)
    with caplog.at_level(logging.DEBUG):
        assert (
            rdp_checks.authenticate("192.0.2.5", "isard", SECRET)["result"]
            == "unreachable"
        )
    assert caplog.records and SECRET not in caplog.text


def test_the_reported_state_never_carries_the_credentials():
    checks, reports = _checks(
        [("auth_failed", "nla", "errconnect_logon_failure", None)]
    )
    checks.observe(_domain(password=SECRET))
    checks._run_one("d1")
    assert (
        reports
        and SECRET not in json.dumps(reports)
        and "isard" not in json.dumps(reports[0][2])
    )


def test_no_credentials_are_sent_once_the_address_is_no_longer_the_desktops():
    calls = []
    result = rdp_checks.verdict(
        "192.0.2.5",
        "isard",
        SECRET,
        probe=lambda ip: ("answers", "nla"),
        authenticate=lambda *a: calls.append(a),
        still_current=lambda: False,
    )
    assert result == ("waiting", "nla", "ip_changed", True)
    assert calls == []


def test_the_address_must_still_be_the_lease_of_that_desktop(tmp_path, monkeypatch):
    leases = tmp_path / "vlan-wg.leases"
    monkeypatch.setattr(rdp_checks, "LEASES", str(leases))
    checks, _ = _checks([])
    checks.observe(_domain())
    fingerprint = checks._desktops["d1"]["fingerprint"]

    leases.write_text(f"1999999999 {MAC} 192.0.2.5 * *\n")
    assert checks._still_current("d1", fingerprint)

    leases.write_text(
        f"1999999999 {MAC} 192.0.2.9 * *\n1999999999 52:54:00:00:00:01 192.0.2.5 * *\n"
    )
    assert not checks._still_current("d1", fingerprint)

    leases.write_text("")
    assert not checks._still_current("d1", fingerprint)


def test_a_new_address_for_the_desktop_invalidates_a_check_in_flight():
    checks, _ = _checks([])
    checks.observe(_domain())
    fingerprint = checks._desktops["d1"]["fingerprint"]
    checks.observe(_domain(ip="192.0.2.6"))
    assert not checks._still_current("d1", fingerprint)
