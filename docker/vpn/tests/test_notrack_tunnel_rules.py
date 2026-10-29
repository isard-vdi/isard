# SPDX-License-Identifier: AGPL-3.0-or-later
"""The NOTRACK block of run.sh, run against a fake iptables.

An outgoing tunnel/geneve packet leaves with ``--dport <port>`` and a hashed
source port, so a NOTRACK rule matching only ``--sport`` never sees it and the
conntrack table fills. These assert on the argv the real run.sh hands iptables:
``--dport`` NOTRACK in OUTPUT for every tunnel + geneve port, and that a replay
adds nothing (the ``-C`` guard holds).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RUN_SH = Path(__file__).resolve().parents[1] / "run.sh"

# A fake iptables that models -t raw -C/-I idempotency in a JSON state file and
# logs every call. -C exits 0 iff an equivalent rule was inserted before; -I
# records it. Normalisation drops the verb and the -I insert index so a -C made
# after an -I of the same rule matches.
_FAKE_IPTABLES = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
open(os.environ["FAKE_IPT_LOG"], "a").write(" ".join(args) + "\n")
def norm(a):
    out, i = [], 0
    while i < len(a):
        t = a[i]
        if t in ("-C", "-I", "-A", "-D"):
            out.append("CHAIN:" + a[i + 1]); i += 2
            if t == "-I" and i < len(a) and a[i].isdigit(): i += 1
            continue
        out.append(t); i += 1
    return out
verb = next((t for t in args if t in ("-C", "-I", "-A", "-D")), None)
sp = os.environ["FAKE_IPT_STATE"]
try:
    rules = json.load(open(sp))
except Exception:
    rules = []
key = norm(args)
if verb == "-C":
    sys.exit(0 if key in rules else 1)
if verb in ("-I", "-A"):
    if key not in rules:
        rules.append(key); json.dump(rules, open(sp, "w"))
sys.exit(0)
"""


def _notrack_block(script: Path) -> str:
    """Extract the lines between the 'Applying NOTRACK' and 'NOTRACK applied'
    echoes — the self-contained rule-installing block, without the daemons."""
    lines = script.read_text().splitlines()
    start = next(
        i for i, l in enumerate(lines) if "Applying NOTRACK rules for tunnel" in l
    )
    end = next(i for i, l in enumerate(lines) if "NOTRACK applied" in l)
    return "\n".join(lines[start + 1 : end])


def _run(tmp_path, env):
    fake = tmp_path / "iptables"
    fake.write_text(_FAKE_IPTABLES)
    fake.chmod(0o755)
    state = tmp_path / "state.json"
    log = tmp_path / "log.txt"
    runenv = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_IPT_STATE": str(state),
        "FAKE_IPT_LOG": str(log),
        **env,
    }
    block = _notrack_block(RUN_SH)
    # Replay to prove idempotency: two passes must leave one rule each.
    for _ in range(2):
        subprocess.run(["sh", "-c", block], env=runenv, check=True)
    inserts = [l for l in log.read_text().splitlines() if " -I " in l]
    return inserts


def _has(inserts, chain, spec, port):
    return any(f"-I {chain} " in i and f"{spec} {port} " in f"{i} " for i in inserts)


def test_outgoing_tunnel_ports_are_notracked_by_dport(tmp_path):
    inserts = _run(tmp_path, {"WG_USERS_PORT": "20016", "WG_HYPERS_PORT": "4443"})
    # The fix: OUTPUT --dport for both on-the-wire tunnel ports.
    assert _has(inserts, "OUTPUT", "--dport", "20016")
    assert _has(inserts, "OUTPUT", "--dport", "4443")


def test_geneve_overlay_port_is_notracked_both_directions(tmp_path):
    inserts = _run(tmp_path, {"WG_USERS_PORT": "20016", "WG_HYPERS_PORT": "4443"})
    # 6081 geneve (bastion/samba + geneve-in-wg) tracked at rest -> NOTRACK both ways.
    assert _has(inserts, "PREROUTING", "--dport", "6081")
    assert _has(inserts, "OUTPUT", "--dport", "6081")


def test_notrack_block_is_idempotent(tmp_path):
    inserts = _run(tmp_path, {"WG_USERS_PORT": "20016", "WG_HYPERS_PORT": "4443"})
    # Two passes, yet each distinct rule inserted exactly once (the -C guard).
    assert inserts, "expected NOTRACK inserts"
    assert len(inserts) == len(
        set(inserts)
    ), "a replay duplicated a NOTRACK rule: " + repr(inserts)
