#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``update_fingerprint`` must not destroy the stored key before it has a new one.

The entry in ``known_hosts`` is the only way the control plane reaches a
hypervisor, and ``ssh-keyscan`` is an unauthenticated connection that OpenSSH 10
penalises per source by default. Deleting the entry first therefore turned every
transient scan failure into a worse state than before, and the retry that
followed scanned again and deepened the block it was trying to get past.

Three behaviours, each the failure mode it prevents:

* a scan that fails (or answers empty) leaves the stored entry **untouched**;
* an unchanged key is **not** rewritten, and costs no ``ssh-keygen -R``;
* a changed key replaces the old entry, by hostname and by address.

Only the subprocess boundary is stubbed: the function under test runs for real.
"""

import pytest

VELLA = "[hyp.example]:2022 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABlaclauvella"
NOVA = "[hyp.example]:2022 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABlaclaunova"


@pytest.fixture
def fingerprint_env(monkeypatch, tmp_path):
    """Point the function at a temp known_hosts and record every subprocess call."""
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(VELLA + "\n")

    calls = []
    scan_result = {"out": NOVA, "raise": False}

    def fake_check_output(args, **kwargs):
        calls.append(tuple(args))
        if args[0] == "ssh-keyscan":
            if scan_result["raise"]:
                raise OSError("boom")
            return scan_result["out"]
        if args[0] == "ssh-keygen":
            # -R removes the matching lines, like the real one does
            path = args[args.index("-f") + 1]
            host = args[args.index("-R") + 1]
            kept = [
                line
                for line in open(path).read().splitlines()
                if not line.startswith(host)
            ]
            open(path, "w").write("\n".join(kept) + ("\n" if kept else ""))
            return ""
        raise AssertionError(f"ordre inesperada: {args}")

    monkeypatch.setattr(mod, "check_output", fake_check_output)
    monkeypatch.setattr(mod.socket, "gethostbyname", lambda h: "192.0.2.10")
    monkeypatch.setattr(mod.os.path, "exists", lambda p: True)

    original = mod.HypervisorsProcessed.update_fingerprint.__func__

    def run(hostname="hyp.example", port="2022"):
        # the SSRF guard resolves the hostname; 192.0.2.10 is TEST-NET-1, public
        monkeypatch.setattr(
            mod.HypervisorsProcessed, "update_fingerprint", classmethod(original)
        )
        import socket as _socket

        monkeypatch.setattr(
            _socket,
            "getaddrinfo",
            lambda *a, **k: [(2, 1, 6, "", ("192.0.2.10", 0))],
        )
        real_open = open

        def open_at_path(p, *a, **k):
            if p == "/sshkeys/known_hosts":
                p = str(known_hosts)
            return real_open(p, *a, **k)

        monkeypatch.setattr("builtins.open", open_at_path)
        try:
            return mod.HypervisorsProcessed.update_fingerprint(hostname, port)
        finally:
            monkeypatch.undo()

    return run, known_hosts, calls, scan_result


def test_una_exploracio_fallida_no_esborra_la_clau_desada(fingerprint_env):
    """El mode de fallada que ens va costar dues hores: la clau bona desapareix."""
    run, known_hosts, calls, scan = fingerprint_env
    scan["raise"] = True

    assert run() is False
    assert known_hosts.read_text().strip() == VELLA, "ha esborrat la clau bona"
    assert not [c for c in calls if c[0] == "ssh-keygen"], "no havia de tocar el fitxer"


def test_una_exploracio_buida_tambe_es_una_fallada(fingerprint_env):
    """ssh-keyscan surt amb 0 i sense res quan el host no ofereix aquell tipus de clau."""
    run, known_hosts, calls, scan = fingerprint_env
    scan["out"] = ""

    assert run() is False
    assert known_hosts.read_text().strip() == VELLA


def test_una_clau_que_no_ha_canviat_no_es_reescriu(fingerprint_env):
    """És el cas normal, i és el que treu les ràfegues d'exploracions."""
    run, known_hosts, calls, scan = fingerprint_env
    known_hosts.write_text(NOVA + "\n")

    assert run() is True
    assert known_hosts.read_text().strip() == NOVA
    assert not [c for c in calls if c[0] == "ssh-keygen"], "no calia tocar res"


def test_una_clau_que_ha_canviat_substitueix_la_vella(fingerprint_env):
    """I quan de debò canvia, s'ha de reemplaçar per nom i per adreça."""
    run, known_hosts, calls, scan = fingerprint_env

    assert run() is True
    contingut = known_hosts.read_text()
    assert NOVA in contingut
    assert VELLA not in contingut
    esborrats = [c for c in calls if c[0] == "ssh-keygen"]
    assert len(esborrats) == 2, "cal esborrar per nom i per adreça"
