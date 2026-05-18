"""Unit tests for api_hypervisors._overlay_max.

`api_hypervisors` cannot be imported bare (api/__init__ boots Flask). Mirroring
api_xml_sections_test.py's `_load_module` philosophy, we evaluate ONLY the
self-contained pure helper block (overhead constants + _overlay_max) extracted
from the module source via runpy — no Flask/RethinkDB needed. The bash twin in
docker/vpn/ovs/ovs_setup.sh must stay consistent with these expectations (see
the Part D consistency matrix).
"""

import os
import re
import runpy
import tempfile
import types

import pytest


def _load_overlay_max():
    src = open(os.path.join(os.path.dirname(__file__), "api_hypervisors.py")).read()
    block = re.search(
        r"_GENEVE_OH = 54.*?return max\(1280, min\(raw, 9000\)\)", src, re.S
    )
    assert block, "could not locate _overlay_max block in api_hypervisors.py"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(block.group(0) + "\n")
        tmp_path = tmp.name
    try:
        ns = runpy.run_path(tmp_path, run_name="_overlay_max_under_test")
    finally:
        os.unlink(tmp_path)
    return types.SimpleNamespace(**ns)


m = _load_overlay_max()


@pytest.mark.parametrize(
    "infra, mode, expected",
    [
        # default 1500 underlay, both modes
        (1500, "wireguard+geneve", 1386),  # 1500-60-54
        (1500, "geneve", 1446),  # 1500-54
        # jumbo underlay -> high ceiling (dnsmasq caps to 1500 separately)
        (9000, "geneve", 8946),  # 9000-54
        (9000, "wireguard+geneve", 8886),  # 9000-60-54
        (20000, "geneve", 9000),  # sane jumbo cap
        # behind another tunnel
        (1400, "wireguard+geneve", 1286),
        # IPv6 floor
        (1340, "wireguard+geneve", 1280),  # 1340-114=1226 -> 1280
        (1300, "geneve", 1280),  # 1300-54=1246 -> 1280
        # string coercion (env vars arrive as str)
        ("1500", "wireguard+geneve", 1386),
        # legacy VPN_MTU is translated at the call site to infra=VPN_MTU+60;
        # here the resulting infra (1440) flows through normally
        (1440, "wireguard+geneve", 1326),
    ],
)
def test_overlay_max(infra, mode, expected):
    assert m._overlay_max(infra, mode) == expected


def test_overlay_max_is_pure():
    a = m._overlay_max(1500, "wireguard+geneve")
    b = m._overlay_max(1500, "wireguard+geneve")
    assert a == b == 1386
