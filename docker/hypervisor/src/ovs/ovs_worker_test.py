"""Unit tests for ovs-worker.py (loaded via importlib because the script
file uses a hyphen in its name).

Run locally:
    cd docker/hypervisor/src/ovs && python -m pytest ovs_worker_test.py -v
"""

import importlib.util
import os

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_OVS_WORKER_PATH = os.path.join(_THIS_DIR, "ovs-worker.py")

_spec = importlib.util.spec_from_file_location("ovs_worker", _OVS_WORKER_PATH)
ovs_worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ovs_worker)


def _worker_without_init():
    """Bypass OvsWorker.__init__ (which shells out to ovs-vsctl); the
    methods under test do not depend on instance attributes."""
    return object.__new__(ovs_worker.OvsWorker)


def _domain_xml(mappings_xml: str) -> str:
    return (
        "<domain>"
        "<metadata>"
        '<isard:isard xmlns:isard="http://isardvdi.com">'
        f"<isard:mac2network>{mappings_xml}</isard:mac2network>"
        "</isard:isard>"
        "</metadata>"
        "</domain>"
    )


# lab_opts key -> the lab_* attribute name carried on <isard:mapping>.
_LAB_ATTR_NAMES = {
    "mac_spoofing": "lab_mac_spoofing",
    "stp_bpdu": "lab_stp_bpdu",
    "broadcast_unlimited": "lab_bcast_unlimited",
    "multicast_unlimited": "lab_mcast_unlimited",
}
_LAB_FLAGS = list(_LAB_ATTR_NAMES)


def _lab_attrs(**flags) -> str:
    """Build the lab_* XML attribute string; values are used verbatim,
    e.g. _lab_attrs(mac_spoofing="true", stp_bpdu="false")."""
    return "".join(f' {_LAB_ATTR_NAMES[k]}="{v}"' for k, v in flags.items())


def _all_lab_attrs(value: str) -> str:
    return _lab_attrs(**{f: value for f in _LAB_FLAGS})


# --------------------------------------------------------------------------
# _parse_mac2network_metadata: lab_* attributes -> iface["lab_opts"] dict
# --------------------------------------------------------------------------


def test_parse_mac2network_all_lab_flags_true():
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:01" kind="interface"'
        ' interface_id="if-lab" vlan_id="1002"' + _all_lab_attrs("true") + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert parsed["52:54:00:aa:bb:01"]["lab_opts"] == {f: True for f in _LAB_FLAGS}


def test_parse_mac2network_all_lab_flags_false_explicit():
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:02" kind="interface"'
        ' interface_id="if-prod" vlan_id="1003"' + _all_lab_attrs("false") + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert parsed["52:54:00:aa:bb:02"]["lab_opts"] == {f: False for f in _LAB_FLAGS}


def test_parse_mac2network_lab_flags_missing_default_false():
    """Legacy XML (pre-feature) has no lab_* attributes -> every flag False."""
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:03" kind="interface"'
        ' interface_id="if-legacy" vlan_id="1004"/>'
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert parsed["52:54:00:aa:bb:03"]["lab_opts"] == {f: False for f in _LAB_FLAGS}


@pytest.mark.parametrize("flag", _LAB_FLAGS)
def test_parse_mac2network_single_flag(flag):
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:07" kind="interface"'
        ' interface_id="if" vlan_id="1002"' + _lab_attrs(**{flag: "true"}) + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    lab = parsed["52:54:00:aa:bb:07"]["lab_opts"]
    assert lab[flag] is True
    assert all(lab[other] is False for other in _LAB_FLAGS if other != flag)


@pytest.mark.parametrize("raw_value", ["true", "TRUE", "True", "tRuE"])
def test_parse_mac2network_lab_flag_case_insensitive(raw_value):
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:04" kind="interface"'
        ' interface_id="if" vlan_id="1005"' + _lab_attrs(mac_spoofing=raw_value) + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert parsed["52:54:00:aa:bb:04"]["lab_opts"]["mac_spoofing"] is True


@pytest.mark.parametrize("raw_value", ["1", "yes", "on", "garbage", ""])
def test_parse_mac2network_lab_flag_non_true_strings_are_false(raw_value):
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:05" kind="interface"'
        ' interface_id="if" vlan_id="1006"' + _lab_attrs(mac_spoofing=raw_value) + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert parsed["52:54:00:aa:bb:05"]["lab_opts"]["mac_spoofing"] is False


def test_parse_mac2network_user_network_has_no_lab_opts():
    """kind="user_network" is wireguard infrastructure; lab options never
    apply there and the parser must not expose a lab_opts dict for it."""
    xml = _domain_xml(
        '<isard:mapping mac="52:54:00:aa:bb:06" kind="user_network"'
        ' network_id="net-x" metadata_id="42"' + _all_lab_attrs("true") + "/>"
    )
    parsed = _worker_without_init()._parse_mac2network_metadata(xml)
    assert (
        "lab_opts" not in parsed["52:54:00:aa:bb:06"]
    ), "wireguard/user_network must never expose lab options"


# --------------------------------------------------------------------------
# _parse_interfaces propagates lab_opts into iface dicts
# --------------------------------------------------------------------------


def _full_domain_xml(target_dev: str, mac: str, lab_attrs: str = ""):
    return f"""<domain>
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:mac2network>
        <isard:mapping mac="{mac}" kind="interface"
                       interface_id="if-x" vlan_id="1002"{lab_attrs}/>
      </isard:mac2network>
    </isard:isard>
  </metadata>
  <devices>
    <interface type="ethernet">
      <mac address="{mac}"/>
      <target dev="{target_dev}"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""


def test_parse_interfaces_propagates_lab_opts():
    xml = _full_domain_xml(
        "vnet99", "52:54:00:00:01:01", _lab_attrs(mac_spoofing="true")
    )
    interfaces = _worker_without_init()._parse_interfaces(xml)
    assert len(interfaces) == 1
    assert interfaces[0]["lab_opts"]["mac_spoofing"] is True
    assert interfaces[0]["lab_opts"]["stp_bpdu"] is False


def test_parse_interfaces_lab_opts_missing_defaults_all_false():
    """Legacy domain XML without lab_* attributes -> all flags False."""
    xml = _full_domain_xml("vnet99", "52:54:00:00:01:03", lab_attrs="")
    interfaces = _worker_without_init()._parse_interfaces(xml)
    assert interfaces[0]["lab_opts"] == {f: False for f in _LAB_FLAGS}


# --------------------------------------------------------------------------
# _flow_add: flag-driven flow set
# --------------------------------------------------------------------------


def _domain_xml_with_vlan(mac: str, vlan_id: str, lab_attrs: str = ""):
    """Like _full_domain_xml but with a configurable vlan_id."""
    return f"""<domain>
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:mac2network>
        <isard:mapping mac="{mac}" kind="interface"
                       interface_id="if-x" vlan_id="{vlan_id}"{lab_attrs}/>
      </isard:mac2network>
    </isard:isard>
  </metadata>
  <devices>
    <interface type="ethernet">
      <mac address="{mac}"/>
      <target dev="vnet42"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""


# ofport stubbed to 42 -> meter_base = 100 + 42*10 = 520
_OFPORT = 42
_METER_BASE = 100 + _OFPORT * 10
_METER_BCAST = _METER_BASE + 2
_METER_MCAST = _METER_BASE + 3
_METER_UNICAST = _METER_BASE + 4


def _worker_ready_for_flow_add(monkeypatch, captured_flows, captured_meters):
    """Build a worker with __init__ bypassed and every dependency of
    _flow_add stubbed so the only observable side effects are the list of
    OpenFlow rules (captured_flows) and the meter specs (captured_meters)."""
    import threading
    from collections import defaultdict

    worker = _worker_without_init()
    worker.domains = defaultdict(ovs_worker.DomainState)
    worker.lock = threading.Lock()
    worker.process_queue = type("Q", (), {"qsize": staticmethod(lambda: 0)})()
    worker.guests_infra_cidr = "10.0.0.0/24"
    worker.geneve_port = "9"
    worker._add_port_to_ovs = lambda *a, **k: True
    worker._get_port_ofport = lambda port: _OFPORT
    worker._set_port_tag = lambda *a, **k: None
    worker._ofctl_mod_port = lambda *a, **k: True

    # BPDU-tunnel side effects (groups, from-geneve flow, port RSTP) go through
    # _ofctl / _set_port_rstp_enable, not the captured add-flows; record them.
    worker._rstp_calls = []
    worker._set_port_rstp_enable = lambda port, enabled: worker._rstp_calls.append(
        (port, enabled)
    )
    worker._ofctl_calls = []
    worker._ofctl = lambda *args: (worker._ofctl_calls.append(args), True)[1]
    worker._ofctl_del_flows = lambda matches: worker._ofctl_calls.append(
        ("del-flows", tuple(matches))
    )

    def fake_create_meters_batch(specs):
        captured_meters.extend(specs)
        return list(specs)

    worker._create_meters_batch = fake_create_meters_batch

    def fake_subprocess_run(cmd, **kwargs):
        if "add-flows" in cmd and kwargs.get("input"):
            captured_flows.extend(kwargs["input"].decode().strip().splitlines())
        return type("CP", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(ovs_worker.subprocess, "run", fake_subprocess_run)
    return worker


def _meter_rate(meters, meter_id):
    for spec in meters:
        if spec[0] == meter_id:
            return spec[1]
    return None


def test_flow_add_default_is_strict(monkeypatch):
    """No lab options -> the strict anti-MAC-spoofing set, unchanged."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add("dom", _domain_xml_with_vlan("52:54:00:00:10:01", "1002"))

    assert any(f"priority=198,in_port={_OFPORT},dl_src=" in f for f in flows)
    assert any("priority=197" in f and "actions=drop" in f for f in flows)
    assert not any("priority=201" in f for f in flows)
    assert not any("priority=202" in f for f in flows)


def test_flow_add_mac_spoofing_emits_permissive(monkeypatch):
    """mac_spoofing outside VLAN 4095 -> no priority=197 drop, no dl_src
    gate; permissive 200-202 set + unicast meter."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:02", "1002", _lab_attrs(mac_spoofing="true")
        ),
    )

    assert not any("priority=197" in f and "actions=drop" in f for f in flows)
    assert not any("dl_src=" in f and "priority=198" in f for f in flows)
    assert any("priority=200" in f and "meter:" in f for f in flows)
    assert any("priority=202" in f for f in flows)
    assert _meter_rate(meters, _METER_UNICAST) == ovs_worker.MAC_SPOOF_UNICAST_RATE


def test_flow_add_mac_spoofing_unicast_has_no_in_port(monkeypatch):
    """Regression for the over-reflection defect: the priority=200 unicast
    catch-all must NOT carry IN_PORT — NORMAL already delivers cross-port
    unicast, and IN_PORT would echo every unicast back to the sender."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:02", "1002", _lab_attrs(mac_spoofing="true")
        ),
    )
    unicast = [f for f in flows if "priority=200" in f]
    assert unicast, "expected a priority=200 unicast catch-all; flows: " + repr(flows)
    for f in unicast:
        assert "IN_PORT" not in f, "unicast catch-all must not reflect to in_port: " + f
        assert "NORMAL" in f


def test_flow_add_mac_spoofing_bcast_mcast_keep_hairpin(monkeypatch):
    """Broadcast (202) / multicast (201) keep NORMAL,IN_PORT so sibling
    endpoints sharing one OVS port (GNS3 cloud) still receive the flood."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:02", "1002", _lab_attrs(mac_spoofing="true")
        ),
    )
    flood = [
        f
        for f in flows
        if ("priority=202" in f and "ff:ff:ff:ff:ff:ff" in f)
        or ("priority=201" in f and "01:00:00:00:00:00/01:00:00:00:00:00" in f)
    ]
    assert len(flood) == 2, "expected non-KVM bcast(202)+mcast(201): " + repr(flows)
    assert all("NORMAL,IN_PORT" in f for f in flood)


def test_flow_add_mac_spoofing_kvm_oui_guard(monkeypatch):
    """mac_spoofing must drop OTHER IsardVDI/KVM (52:54:00) source MACs so a
    lab VM cannot impersonate another desktop, while still allowing this
    desktop's own MAC and keeping non-KVM source MACs permissive."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    mac = "52:54:00:00:10:02"
    worker._flow_add(
        "dom", _domain_xml_with_vlan(mac, "1002", _lab_attrs(mac_spoofing="true"))
    )
    # priority=203: drop any 52:54:00 source MAC (other desktops)
    assert any(
        "priority=203" in f
        and "dl_src=52:54:00:00:00:00/ff:ff:ff:00:00:00" in f
        and "actions=drop" in f
        for f in flows
    ), "expected priority=203 KVM-OUI source drop; flows: " + repr(flows)
    # own-MAC allowed above the drop: 206 bcast + 205 mcast + 204 unicast,
    # all scoped to dl_src=mac
    assert any(
        "priority=206" in f and f"dl_src={mac}" in f and "ff:ff:ff:ff:ff:ff" in f
        for f in flows
    ), "expected own-MAC bcast allow; flows: " + repr(flows)
    assert any(
        "priority=205" in f
        and f"dl_src={mac}" in f
        and "01:00:00:00:00:00/01:00:00:00:00:00" in f
        for f in flows
    ), "expected own-MAC mcast allow; flows: " + repr(flows)
    assert any(
        "priority=204" in f and f"dl_src={mac}" in f for f in flows
    ), "expected own-MAC unicast allow; flows: " + repr(flows)
    # non-KVM catch-all (200 unicast no IN_PORT, 202 bcast, 201 mcast)
    assert any(
        "priority=200" in f and "NORMAL" in f and "IN_PORT" not in f for f in flows
    )
    assert any("priority=202" in f and "ff:ff:ff:ff:ff:ff" in f for f in flows)
    assert any(
        "priority=201" in f and "01:00:00:00:00:00/01:00:00:00:00:00" in f
        for f in flows
    )


def test_flow_add_mac_spoofing_bcast_strictly_above_mcast(monkeypatch):
    """ff:ff:ff:ff:ff:ff also satisfies the 01:00:.../01:00:... multicast
    mask; equal-priority overlap is undefined in OpenFlow, so the broadcast
    flow must sit strictly ABOVE its multicast sibling in every layer
    (own-MAC 206>205, non-KVM 202>201) so a broadcast storm is always
    accounted to the broadcast meter."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:02", "1002", _lab_attrs(mac_spoofing="true")
        ),
    )
    import re

    bcast = {
        int(re.search(r"priority=(\d+)", f).group(1))
        for f in flows
        if "ff:ff:ff:ff:ff:ff" in f
    }
    mcast = {
        int(re.search(r"priority=(\d+)", f).group(1))
        for f in flows
        if "01:00:00:00:00:00/01:00:00:00:00:00" in f
    }
    assert not bcast & mcast, (
        "broadcast and multicast flows must never share a priority: "
        f"bcast={bcast} mcast={mcast}"
    )


def test_flow_add_strict_bcast_strictly_above_mcast(monkeypatch):
    """Strict mode: broadcast meter flow at 200, multicast at 199 — never the
    same priority (broadcast also matches the multicast mask)."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add("dom", _domain_xml_with_vlan("52:54:00:00:10:01", "1002"))
    assert any(
        "priority=200" in f and "ff:ff:ff:ff:ff:ff" in f and "meter:" in f
        for f in flows
    ), "expected strict bcast meter flow at 200; flows: " + repr(flows)
    assert any(
        "priority=199" in f
        and "01:00:00:00:00:00/01:00:00:00:00:00" in f
        and "meter:" in f
        for f in flows
    )
    assert not any("priority=199" in f and "ff:ff:ff:ff:ff:ff" in f for f in flows)


def test_flow_add_user_network_bcast_strictly_above_mcast(monkeypatch):
    """user_network (wireguard) metadata mode: same split, bcast 200 over
    mcast 199."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    mac = "52:54:00:00:10:08"
    xml = f"""<domain>
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:mac2network>
        <isard:mapping mac="{mac}" kind="user_network"
                       network_id="net-x" metadata_id="42"/>
      </isard:mac2network>
    </isard:isard>
  </metadata>
  <devices>
    <interface type="ethernet">
      <mac address="{mac}"/>
      <target dev="vnet42"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>"""
    worker._flow_add("dom", xml)
    assert any(
        "priority=200" in f and "ff:ff:ff:ff:ff:ff" in f and "meter:" in f
        for f in flows
    ), "expected user_network bcast meter flow at 200; flows: " + repr(flows)
    assert any(
        "priority=199" in f
        and "01:00:00:00:00:00/01:00:00:00:00:00" in f
        and "meter:" in f
        for f in flows
    )
    assert not any("priority=199" in f and "ff:ff:ff:ff:ff:ff" in f for f in flows)


def test_flow_add_every_port_drops_forged_tunnel_mac(monkeypatch):
    """A guest must never source frames to BPDU_TUNNEL_MAC: it is multicast
    (flooded over geneve by the mcast catch-alls) and the remote from-geneve
    flow would rewrite it into a genuine BPDU on the far side. Every port
    kind gets a priority=250 ingress drop for it."""
    cases = [
        ("strict", _domain_xml_with_vlan("52:54:00:00:10:0a", "1002")),
        (
            "mac_spoofing",
            _domain_xml_with_vlan(
                "52:54:00:00:10:0b", "1002", _lab_attrs(mac_spoofing="true")
            ),
        ),
        (
            "stp_bpdu",
            _domain_xml_with_vlan(
                "52:54:00:00:10:0c", "1002", _lab_attrs(stp_bpdu="true")
            ),
        ),
        (
            "vlan4095",
            _domain_xml_with_vlan("52:54:00:00:10:0d", "4095"),
        ),
        (
            "user_network",
            """<domain>
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:mac2network>
        <isard:mapping mac="52:54:00:00:10:0e" kind="user_network"
                       network_id="net-x" metadata_id="42"/>
      </isard:mac2network>
    </isard:isard>
  </metadata>
  <devices>
    <interface type="ethernet">
      <mac address="52:54:00:00:10:0e"/>
      <target dev="vnet42"/>
      <model type="virtio"/>
    </interface>
  </devices>
</domain>""",
        ),
    ]
    for label, xml in cases:
        flows, meters = [], []
        worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
        worker._flow_add("dom-" + label, xml)
        assert any(
            "priority=250" in f
            and f"dl_dst={ovs_worker.BPDU_TUNNEL_MAC}" in f
            and "actions=drop" in f
            for f in flows
        ), f"expected forged-tunnel-MAC drop for {label}; flows: " + repr(flows)


def test_flow_add_strict_has_no_kvm_oui_guard(monkeypatch):
    """The 52:54:00 OUI drop is a mac_spoofing-only construct; strict mode
    (default) must not emit it."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add("dom", _domain_xml_with_vlan("52:54:00:00:10:09", "1002"))
    assert not any("priority=203" in f for f in flows)
    assert not any("ff:ff:ff:00:00:00" in f for f in flows)


def test_flow_add_vlan_4095_ignores_all_lab_flags(monkeypatch):
    """Central security invariant: every lab flag is ignored on VLAN 4095
    (wireguard infra) — always strict priority=197 drop, never 201/202."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom-4095",
        _domain_xml_with_vlan("52:54:00:00:40:95", "4095", _all_lab_attrs("true")),
    )
    assert any("priority=197" in f and "actions=drop" in f for f in flows)
    assert not any("priority=201" in f for f in flows)
    assert not any("priority=202" in f for f in flows)
    assert not any("priority=203" in f for f in flows)  # no mac_spoofing KVM guard
    # stp_bpdu is also ignored on 4095: no tunnel ingress flow, no group built.
    assert not any("priority=251" in f for f in flows)
    assert not worker._ofctl_calls


def test_flow_add_broadcast_unlimited_raises_bcast_meter(monkeypatch):
    """broadcast_unlimited raises the broadcast meter to the lab ceiling,
    independently of mac_spoofing (strict flows still present)."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:03", "1002", _lab_attrs(broadcast_unlimited="true")
        ),
    )
    assert _meter_rate(meters, _METER_BCAST) == ovs_worker.BCAST_LAB_RATE
    # mac_spoofing was NOT set -> strict set still applies
    assert any("priority=197" in f and "actions=drop" in f for f in flows)


def test_flow_add_multicast_unlimited_raises_mcast_meter(monkeypatch):
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan(
            "52:54:00:00:10:04", "1002", _lab_attrs(multicast_unlimited="true")
        ),
    )
    assert _meter_rate(meters, _METER_MCAST) == ovs_worker.MCAST_LAB_RATE


def test_flow_add_default_meters_are_storm_protection(monkeypatch):
    """Without lab flags the bcast/mcast meters keep their strict defaults."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add("dom", _domain_xml_with_vlan("52:54:00:00:10:05", "1002"))
    assert _meter_rate(meters, _METER_BCAST) == 10
    assert _meter_rate(meters, _METER_MCAST) == 500


# --------------------------------------------------------------------------
# _flow_add: BPDU tunneling (stp_bpdu)
# --------------------------------------------------------------------------

_METER_BPDU = _METER_BASE + 5


def test_flow_add_stp_bpdu_ingress_meter_and_rstp(monkeypatch):
    """stp_bpdu installs the priority=251 ingress flow targeting the per-VLAN
    ALL group, meters it, and disables port-level RSTP so ovsbr0 does not eat
    the guest BPDU."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan("52:54:00:00:10:06", "1002", _lab_attrs(stp_bpdu="true")),
    )
    ingress = [
        f for f in flows if "priority=251" in f and "in_port=" + str(_OFPORT) in f
    ]
    assert ingress, "expected a priority=251 BPDU ingress flow; flows: " + repr(flows)
    assert any("dl_dst=01:80:c2:00:00:00" in f and "group:1002" in f for f in ingress)
    assert _meter_rate(meters, _METER_BPDU) == ovs_worker.BPDU_TUNNEL_RATE
    # port-level RSTP disabled
    assert (
        "vnet42",
        False,
    ) in worker._rstp_calls or any(not en for (_, en) in worker._rstp_calls)


def test_flow_add_stp_bpdu_builds_groups_and_geneve_flow(monkeypatch):
    """stp_bpdu (re)builds both per-VLAN groups (ALL=vlan, LOCAL=8000+vlan) and
    installs the from-geneve reverse-rewrite flow."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan("52:54:00:00:10:07", "1002", _lab_attrs(stp_bpdu="true")),
    )
    joined = " || ".join(" ".join(map(str, c)) for c in worker._ofctl_calls)
    # ALL group: local port + geneve rewrite bucket
    assert "group_id=1002,type=all" in joined
    assert "mod_dl_dst:" + ovs_worker.BPDU_TUNNEL_MAC in joined
    assert "output:" + str(_OFPORT) in joined
    # LOCAL group: id 8000+vlan
    assert "group_id=9002,type=all" in joined
    # from-geneve reverse-rewrite flow back to the canonical BPDU MAC
    assert "dl_dst=" + ovs_worker.BPDU_TUNNEL_MAC in joined
    assert "mod_dl_dst:01:80:c2:00:00:00" in joined


def test_sync_bpdu_groups_geneve_bucket_pushes_vlan_tag(monkeypatch):
    """The geneve bucket egresses via a raw output: action, which bypasses
    the access-port tagging that only NORMAL applies — so the bucket itself
    must push the VLAN tag (mod_vlan_vid) or the remote from-geneve flow
    (dl_vlan=N) can never match and the tunnel silently drops every BPDU."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan("52:54:00:00:10:07", "1002", _lab_attrs(stp_bpdu="true")),
    )
    group_calls = [
        " ".join(map(str, c))
        for c in worker._ofctl_calls
        if "group_id=1002,type=all" in " ".join(map(str, c))
    ]
    assert group_calls, "ALL group was not built: " + repr(worker._ofctl_calls)
    all_group = group_calls[-1]
    # geneve bucket: rewrite + tag push + output to the geneve trunk
    assert (
        f"mod_dl_dst:{ovs_worker.BPDU_TUNNEL_MAC},mod_vlan_vid:1002,output:9"
        in all_group
    ), ("geneve bucket must push the VLAN tag before output: " + all_group)
    # local buckets stay untagged (they feed access ports)
    local_bucket = f"bucket=actions=output:{_OFPORT}"
    assert local_bucket in all_group


def test_sync_bpdu_groups_installs_from_geneve_flood_delivery(monkeypatch):
    """rstp-enable=false on the lab port excludes it from OVS NORMAL's flood
    domain, so cross-host ARP/broadcast/multicast/unlearned-unicast on the
    VLAN never reaches the lab port without an explicit rule. The fix
    installs a priority=200 from-geneve delivery flow that fans out via the
    local-only group (group_id=8000+vlan). It must NOT fall through to NORMAL
    (NORMAL would unicast to a learned lab port and duplicate every learned
    frame)."""
    flows, meters = [], []
    worker = _worker_ready_for_flow_add(monkeypatch, flows, meters)
    worker._flow_add(
        "dom",
        _domain_xml_with_vlan("52:54:00:00:10:08", "1002", _lab_attrs(stp_bpdu="true")),
    )
    add_flow_calls = [
        " ".join(map(str, c)) for c in worker._ofctl_calls if "add-flow" in c
    ]
    delivery = [
        c
        for c in add_flow_calls
        if "priority=200" in c and "in_port=9" in c and "dl_vlan=1002" in c
    ]
    assert delivery, (
        "expected a priority=200 from-geneve delivery add-flow for vlan 1002; "
        "add-flow calls: " + repr(add_flow_calls)
    )
    flow = delivery[0]
    # Must reuse the local-only group (group_id=8000+vlan) so deliveries fan
    # out only to local lab-STP ports, never re-egress to geneve.
    assert "group:9002" in flow, (
        "must reuse group_id=8000+vlan (9002) for from-geneve delivery: " + flow
    )
    # Must strip the VLAN tag before the group hits the access port.
    assert "strip_vlan" in flow, "must strip_vlan before delivering: " + flow
    # MUST NOT fall through to NORMAL — NORMAL learns A's MAC at the lab port
    # on the outgoing direction, then on the reply path unicasts to the same
    # port a second time, duplicating every learned-MAC frame (verified via
    # ofproto/trace: Datapath actions: pop_vlan,N,N).
    assert "NORMAL" not in flow, (
        "from-geneve flood-delivery must NOT fall through to NORMAL: " + flow
    )


def test_sync_bpdu_groups_teardown_when_no_ports(monkeypatch):
    """When the last lab-STP port on a VLAN is gone, _sync_bpdu_groups deletes
    both groups and the from-geneve flow (no dangling tunnel)."""
    import threading
    from collections import defaultdict

    worker = _worker_without_init()
    worker.domains = defaultdict(ovs_worker.DomainState)  # no bpdu ports anywhere
    worker.lock = threading.Lock()
    worker.geneve_port = "9"
    worker._ofctl_calls = []
    worker._ofctl = lambda *args: (worker._ofctl_calls.append(args), True)[1]
    worker._ofctl_del_flows = lambda matches: worker._ofctl_calls.append(
        ("del-flows", tuple(matches))
    )

    worker._sync_bpdu_groups({1002})

    joined = " || ".join(" ".join(map(str, c)) for c in worker._ofctl_calls)
    assert "del-groups" in joined and "group_id=1002" in joined
    assert "group_id=9002" in joined
    assert "del-flows" in joined
    # The teardown del-flows match must be broad enough (no dl_dst constraint)
    # to remove BOTH the priority=251 BPDU rewrite flow AND the new priority=200
    # from-geneve flood-delivery flow with a single call.
    del_calls = [c for c in worker._ofctl_calls if c[0] == "del-flows"]
    assert any(
        any("in_port=9,dl_vlan=1002" in m and "dl_dst=" not in m for m in c[1])
        for c in del_calls
    ), (
        "teardown match must omit dl_dst so it catches the priority=200 flow too: "
        + str(del_calls)
    )
