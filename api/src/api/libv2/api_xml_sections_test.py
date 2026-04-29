"""Unit tests for api_xml_sections split/merge round-trip.

These tests run without booting Flask or RethinkDB by patching out the
problematic imports before evaluating the module source. This mirrors the
approach used by engine/engine/engine/models/domain_xml_test.py for the
engine side, but adapted to the api side where the package init has heavy
side effects.
"""

import os
import runpy
import sys
import tempfile
import textwrap
import types
from xml.etree import ElementTree as ET

import pytest


def _load_module():
    src_path = os.path.join(os.path.dirname(__file__), "api_xml_sections.py")
    src = open(src_path).read()
    src = src.replace(
        "from .api_admin import admin_table_get, db",
        textwrap.dedent(
            """
            class _FakeDB:
                conn = None
            db = _FakeDB()
            def admin_table_get(*a, **kw):
                return {}
            """
        ).strip(),
    )
    src = src.replace("from api import app", "")
    src = src.replace(
        "from isardvdi_common.api_exceptions import Error",
        textwrap.dedent(
            """
            class Error(Exception):
                def __init__(self, code, msg, tb=''):
                    super().__init__(f'{code}:{msg}')
                    self.code = code
                    self.msg = msg
            """
        ).strip(),
    )
    if "rethinkdb" not in sys.modules:
        sys.modules["rethinkdb"] = types.SimpleNamespace(
            RethinkDB=lambda: types.SimpleNamespace(
                table=lambda *a, **kw: None,
                literal=lambda x: x,
            )
        )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(src)
        tmp_path = tmp.name
    try:
        ns = runpy.run_path(tmp_path, run_name="api_xml_sections_under_test")
    finally:
        os.unlink(tmp_path)
    return types.SimpleNamespace(**ns)


m = _load_module()


# ---- helpers ----------------------------------------------------------------


def _toplevel_tag_order(xml_str):
    """Return a list of direct-child tags of <domain> in document order."""
    root = ET.fromstring(xml_str)
    return [child.tag for child in root]


# Self-contained sample so the test does not need network or a fixture file.
SAMPLE_DOMAIN_XML = """<domain xmlns:ns0="http://libosinfo.org/xmlns/libvirt/domain/1.0" type="kvm">
  <name>9d881705-2e33-4531-b85d-83cddfe3526b</name>
  <uuid>d97fd0eb-b726-46b0-8509-ccd259ade9b1</uuid>
  <metadata>
    <ns0:libosinfo>
      <ns0:os id="http://debian.org/debian/12"/>
    </ns0:libosinfo>
  </metadata>
  <memory unit="KiB">8388608</memory>
  <currentMemory unit="KiB">8388608</currentMemory>
  <memoryBacking>
    <source type="memfd"/>
    <access mode="shared"/>
  </memoryBacking>
  <vcpu placement="static">4</vcpu>
  <os>
    <type arch="x86_64" machine="q35">hvm</type>
    <boot dev="hd"/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode="host-passthrough"/>
  <clock offset="utc"/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <pm/>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/isard/templates/x.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <interface type="network">
      <source network="default"/>
      <mac address="52:54:00:11:3f:37"/>
      <model type="virtio"/>
    </interface>
    <channel type="unix">
      <source mode="bind"/>
      <target type="virtio" name="org.qemu.guest_agent.0"/>
    </channel>
    <channel type="spicevmc">
      <target type="virtio" name="com.redhat.spice.0"/>
    </channel>
    <graphics type="spice" autoport="yes"/>
    <video><model type="virtio"/></video>
  </devices>
  <seclabel type="dynamic" model="dac" relabel="yes"/>
</domain>"""


def _roundtrip(base_xml, edit=None):
    """Split the XML, optionally apply edits, merge back."""
    sections = m.split_xml_sections(base_xml, [])
    edited = {s["key"]: s["xml"] for s in sections if s.get("protectable")}
    if edit:
        edited.update(edit)
    return m.merge_xml_sections(base_xml, edited)


# ---- tests ------------------------------------------------------------------


def test_roundtrip_preserves_memorybacking_position():
    """memoryBacking must stay before <vcpu> and before <devices>.

    Regression: before the fix, a no-op Save moved <memoryBacking> to the end
    of <domain> via _merge_catchall_section, breaking GPU desktops on libvirt.
    """
    merged = _roundtrip(SAMPLE_DOMAIN_XML)
    order = _toplevel_tag_order(merged)
    assert "memoryBacking" in order, "memoryBacking lost on round-trip"
    assert order.index("memoryBacking") < order.index(
        "vcpu"
    ), f"memoryBacking moved past <vcpu>: {order}"
    assert order.index("memoryBacking") < order.index(
        "devices"
    ), f"memoryBacking moved past <devices>: {order}"


def test_roundtrip_preserves_lifecycle_position():
    """on_poweroff/on_reboot/on_crash must stay before <devices>."""
    merged = _roundtrip(SAMPLE_DOMAIN_XML)
    order = _toplevel_tag_order(merged)
    devices_idx = order.index("devices")
    for tag in ("on_poweroff", "on_reboot", "on_crash"):
        assert tag in order, f"{tag} lost on round-trip"
        assert order.index(tag) < devices_idx, f"{tag} moved past <devices>: {order}"


def test_roundtrip_preserves_seclabel_after_devices():
    """seclabel must stay after <devices>."""
    merged = _roundtrip(SAMPLE_DOMAIN_XML)
    order = _toplevel_tag_order(merged)
    assert "seclabel" in order, "seclabel lost on round-trip"
    assert order.index("seclabel") > order.index(
        "devices"
    ), f"seclabel moved before <devices>: {order}"


def test_roundtrip_preserves_guest_agent_channel_children():
    """The <channel type='unix'> guest-agent block must keep its
    <source> and <target> children across split+merge."""
    merged = _roundtrip(SAMPLE_DOMAIN_XML)
    root = ET.fromstring(merged)
    targets = root.findall(
        ".//devices/channel[@type='unix']/target[@name='org.qemu.guest_agent.0']"
    )
    assert len(targets) == 1, "guest-agent target lost"
    sources = root.findall(".//devices/channel[@type='unix']/source[@mode='bind']")
    assert len(sources) == 1, "guest-agent source lost"


def test_add_usb_hostdev_persists_through_roundtrip():
    """Pasting a USB hostdev into the Passthrough section persists across
    a save/load cycle, with vendor/product children preserved."""
    snippet = (
        "<hostdev mode='subsystem' type='usb' managed='yes'>\n"
        "  <source>\n"
        "    <vendor id='0x0951'/>\n"
        "    <product id='0x1666'/>\n"
        "  </source>\n"
        "</hostdev>"
    )
    merged = _roundtrip(SAMPLE_DOMAIN_XML, edit={"hostdev": snippet})
    root = ET.fromstring(merged)
    hostdevs = root.findall(".//devices/hostdev[@type='usb']")
    assert len(hostdevs) == 1, "USB hostdev lost after merge"
    assert hostdevs[0].find("source/vendor").get("id") == "0x0951"
    assert hostdevs[0].find("source/product").get("id") == "0x1666"

    # And it must still be there after another split+merge cycle
    merged2 = _roundtrip(merged)
    sections2 = m.split_xml_sections(merged2, [])
    hostdev_section = next(s for s in sections2 if s["key"] == "hostdev")
    assert "vendor" in hostdev_section["xml"]
    assert "product" in hostdev_section["xml"]


def test_add_memory_backing_lands_before_devices():
    """When the base XML has no <memoryBacking>, pasting one in the
    memory_backing section must place it before <devices>, not after."""
    base = """<domain type="kvm">
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory unit="KiB">8388608</memory>
  <currentMemory unit="KiB">8388608</currentMemory>
  <vcpu>2</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices><emulator>/usr/bin/qemu-kvm</emulator></devices>
</domain>"""
    snippet = (
        '<memoryBacking><source type="memfd"/>'
        '<access mode="shared"/></memoryBacking>'
    )
    merged = _roundtrip(base, edit={"memory_backing": snippet})
    order = _toplevel_tag_order(merged)
    assert "memoryBacking" in order
    assert order.index("memoryBacking") < order.index(
        "devices"
    ), f"new memoryBacking landed past <devices>: {order}"
    assert order.index("memoryBacking") > order.index(
        "currentMemory"
    ), f"new memoryBacking landed before <currentMemory>: {order}"


def test_add_seclabel_lands_after_devices():
    """When the base XML has no <seclabel>, pasting one must place it after
    <devices> per libvirt canonical order."""
    base = """<domain type="kvm">
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory>1</memory>
  <currentMemory>1</currentMemory>
  <vcpu>1</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices><emulator>/usr/bin/qemu-kvm</emulator></devices>
</domain>"""
    snippet = '<seclabel type="dynamic" model="dac" relabel="yes"/>'
    merged = _roundtrip(base, edit={"seclabel": snippet})
    order = _toplevel_tag_order(merged)
    assert "seclabel" in order
    assert order.index("seclabel") > order.index("devices")


def test_other_toplevel_unclaimed_keeps_position():
    """An element not claimed by any SECTION_DEFS entry (here <perf>) must end
    up in a valid libvirt position after a round-trip — strictly before
    <devices>, regardless of where the catchall placed it."""
    base = """<domain type="kvm">
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory>1</memory>
  <currentMemory>1</currentMemory>
  <perf><event name="cmt" enabled="yes"/></perf>
  <vcpu>1</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices><emulator>/usr/bin/qemu-kvm</emulator></devices>
</domain>"""
    merged = _roundtrip(base)
    order = _toplevel_tag_order(merged)
    assert "perf" in order
    assert order.index("perf") < order.index(
        "devices"
    ), f"<perf> moved past <devices>: {order}"


def test_wrong_section_paste_is_rejected():
    """Pasting <hostdev> into the redirdev section must raise instead of
    silently relocating the element to the hostdev section on the next split.
    Surfaces the case where a user pastes USB passthrough XML into the wrong
    box and the content appears to vanish."""
    sections = m.split_xml_sections(SAMPLE_DOMAIN_XML, [])
    edited = {s["key"]: s["xml"] for s in sections if s.get("protectable")}
    edited["redirdev"] = (
        '<hostdev mode="subsystem" type="usb" managed="yes">\n'
        '  <source><vendor id="0x0951"/><product id="0x1666"/></source>\n'
        "</hostdev>"
    )
    try:
        m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    except m.Error as e:
        assert "redirdev" in str(e) or "USB Redirectors" in str(e)
        assert "hostdev" in str(e)
        return
    raise AssertionError("merge accepted hostdev in redirdev section")


def test_lifecycle_section_accepts_any_lifecycle_tag():
    """The lifecycle section allows any of on_poweroff, on_reboot, on_crash —
    the validator must not reject a snippet that uses on_reboot only."""
    sections = m.split_xml_sections(SAMPLE_DOMAIN_XML, [])
    edited = {s["key"]: s["xml"] for s in sections if s.get("protectable")}
    edited["lifecycle"] = "<on_reboot>destroy</on_reboot>"
    merged = m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    root = ET.fromstring(merged)
    assert root.find("./on_reboot") is not None


def test_corrupted_input_recovers_canonical_order():
    """If a domain was previously saved by the old (buggy) editor with
    <memoryBacking> ending up after </devices>, a no-op save through the
    current code must move it back ahead of <devices> so libvirt accepts the
    document on next start."""
    bad = """<domain type="kvm">
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory unit="KiB">1</memory>
  <currentMemory unit="KiB">1</currentMemory>
  <vcpu>1</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <pm/>
  <devices><emulator>/usr/bin/qemu-kvm</emulator></devices>
  <memoryBacking><source type="memfd"/></memoryBacking>
  <on_poweroff>destroy</on_poweroff>
</domain>"""
    merged = _roundtrip(bad)
    order = _toplevel_tag_order(merged)
    assert "memoryBacking" in order and "devices" in order
    assert order.index("memoryBacking") < order.index(
        "devices"
    ), f"memoryBacking not normalized ahead of devices: {order}"
    assert order.index("on_poweroff") < order.index(
        "devices"
    ), f"on_poweroff not normalized ahead of devices: {order}"


def test_new_protectable_section_keys_present():
    """All newly added section keys are protectable so the engine honors them."""
    keys = {s["key"] for s in m.SECTION_DEFS if s["protectable"]}
    for k in (
        "memory_backing",
        "max_memory",
        "numatune",
        "cputune",
        "iothreads",
        "lifecycle",
        "seclabel",
        "sysinfo",
        "resource",
        "description",
    ):
        assert k in keys, f"new section {k!r} not protectable"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
