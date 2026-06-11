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


# ---- derived-section tests (Redmine #15065 / journal #89529) ----------------


def test_disks_cache_edit_persists_through_roundtrip():
    """Editing the cache attribute inside the parent <disk> snippet persists
    across merge_xml_sections — i.e. the stale disk_cache snippet does NOT
    silently revert it. This is the asymmetry the reporter hit when "edit
    cache in Disk Cache works, edit cache in Disks doesn't"."""
    sections = m.split_xml_sections(SAMPLE_DOMAIN_XML, [])
    edited = {s["key"]: s["xml"] for s in sections if s.get("protectable")}
    edited["disks"] = (
        '<disk type="file" device="disk">\n'
        '  <driver name="qemu" type="qcow2" cache="writeback"/>\n'
        '  <source file="/isard/templates/x.qcow2"/>\n'
        '  <target dev="vda" bus="virtio"/>\n'
        "</disk>"
    )
    merged = m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    root = ET.fromstring(merged)
    drivers = root.findall('.//devices/disk[@device="disk"]/driver')
    assert len(drivers) == 1
    assert (
        drivers[0].get("cache") == "writeback"
    ), "cache edit via disks snippet was not preserved after merge"


def test_stale_disk_cache_snippet_does_not_clobber_disks_edit():
    """Frontend sends every textarea on save, including unchanged disk_cache.
    With disk_cache in _DERIVED_KEYS the unchanged child snippet must be
    ignored so the parent's cache edit wins, not the stale child."""
    edited = {
        "disks": (
            '<disk type="file" device="disk">'
            '<driver name="qemu" type="qcow2" cache="writeback"/>'
            '<source file="/isard/templates/x.qcow2"/>'
            '<target dev="vda" bus="virtio"/>'
            "</disk>"
        ),
        # The stale disk_cache snippet the frontend would send (untouched
        # by the user) — it carries the OLD <driver> with no cache attribute.
        "disk_cache": '<driver name="qemu" type="qcow2"/>',
    }
    merged = m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    root = ET.fromstring(merged)
    drivers = root.findall('.//devices/disk[@device="disk"]/driver')
    assert len(drivers) == 1
    assert drivers[0].get("cache") == "writeback"


def test_stale_qos_disk_snippet_does_not_clobber_disks_iotune_edit():
    """Same protection for qos_disk: an iotune block added inside the disks
    snippet must survive merge even if a stale qos_disk snippet is also sent."""
    edited = {
        "disks": (
            '<disk type="file" device="disk">'
            '<driver name="qemu" type="qcow2"/>'
            '<source file="/isard/templates/x.qcow2"/>'
            '<target dev="vda" bus="virtio"/>'
            "<iotune><read_bytes_sec>1048576</read_bytes_sec></iotune>"
            "</disk>"
        ),
        # Stale (empty) qos_disk snippet — the textarea was untouched.
        "qos_disk": "",
    }
    merged = m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    root = ET.fromstring(merged)
    iotunes = root.findall('.//devices/disk[@device="disk"]/iotune')
    assert len(iotunes) == 1, "iotune added inside disks snippet was lost"
    assert iotunes[0].find("read_bytes_sec") is not None
    assert iotunes[0].find("read_bytes_sec").text == "1048576"


def test_split_marks_derived_views():
    """split_xml_sections must expose `derived: True` for child-overlap
    sections (disk_cache, qos_disk) and False for stand-alone sections."""
    sections = m.split_xml_sections(SAMPLE_DOMAIN_XML, [])
    by_key = {s["key"]: s for s in sections}
    assert by_key["disk_cache"]["derived"] is True
    assert by_key["qos_disk"]["derived"] is True
    for k in ("disks", "isos", "floppies", "hostdev", "network", "vcpus", "cpu"):
        assert (
            by_key[k]["derived"] is False
        ), f"section {k!r} unexpectedly marked derived"


def test_split_rejects_non_domain_root():
    """Uploaded XML must be a libvirt <domain> document. Earlier code accepted
    any well-formed root and returned every section empty, which the JS then
    reported as a successful load — silently wiping the form."""
    fragment = (
        '<disk type="file" device="disk">'
        '<driver name="qemu" type="qcow2"/>'
        '<source file="/x.qcow2"/>'
        '<target dev="vda" bus="virtio"/>'
        "</disk>"
    )
    try:
        m.split_xml_sections(fragment, [])
    except m.Error as e:
        assert "domain" in str(e).lower()
        assert "disk" in str(e), "error should name the actual root tag"
        return
    raise AssertionError("split accepted a non-<domain> root")


def _canonical(xml_str):
    """Normalized (tag, sorted-attrs, text, children) tree for whitespace/attr
    order-insensitive equality, used by split->merge idempotency assertions."""

    def norm(e):
        return (
            e.tag,
            tuple(sorted(e.attrib.items())),
            (e.text or "").strip(),
            tuple(norm(c) for c in e if not callable(c.tag)),
        )

    return norm(ET.fromstring(xml_str))


# ---- B2: absent device section is inserted under the right parent ----------


_NO_AGENT_BASE = """<domain type="kvm">
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory unit="KiB">8388608</memory>
  <currentMemory unit="KiB">8388608</currentMemory>
  <vcpu placement="static">2</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <channel type="spicevmc">
      <target type="virtio" name="com.redhat.spice.0"/>
    </channel>
  </devices>
</domain>"""


def test_merge_inserts_absent_guest_agent_channel_inside_devices():
    """B2: pasting a guest-agent channel into a base with none must land inside
    <devices>, not as a direct child of <domain> (which libvirt rejects)."""
    snippet = (
        '<channel type="unix">'
        '  <source mode="bind"/>'
        '  <target type="virtio" name="org.qemu.guest_agent.0"/>'
        "</channel>"
    )
    merged = m.merge_xml_sections(_NO_AGENT_BASE, {"qemu_guest_agent": snippet})
    root = ET.fromstring(merged)
    assert (
        root.find("./channel") is None
    ), "channel inserted as direct child of <domain>"
    placed = root.find(
        './devices/channel[@type="unix"]' '/target[@name="org.qemu.guest_agent.0"]/..'
    )
    assert placed is not None, "guest-agent channel not placed inside <devices>"


# ---- B3: comments survive a no-op round-trip -------------------------------


_COMMENT_BASE = """<domain type="kvm">
  <!-- isard: do not edit memoryBacking, GPU desktop -->
  <name>x</name>
  <uuid>00000000-0000-0000-0000-000000000000</uuid>
  <memory unit="KiB">8388608</memory>
  <currentMemory unit="KiB">8388608</currentMemory>
  <vcpu>2</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices><emulator>/usr/bin/qemu-kvm</emulator></devices>
</domain>"""


def test_noop_roundtrip_preserves_comment():
    """B3: an XML comment must survive a no-op split->merge round-trip."""
    merged = _roundtrip(_COMMENT_BASE)
    assert "<!-- isard: do not edit memoryBacking, GPU desktop -->" in merged


# ---- B4: domain_type is editable -------------------------------------------


def test_domain_type_edit_changes_domain_type_attr():
    """B4: editing the encoded type in the domain_type section sets
    <domain type=...>."""
    edited = {
        "domain_type": '<!-- domain type="qemu" -->\n'
        "<emulator>/usr/bin/qemu-system-x86_64</emulator>"
    }
    merged = m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    assert ET.fromstring(merged).get("type") == "qemu"


def test_domain_type_rejects_invalid_type():
    """B4: an unknown domain type must be rejected, not silently applied."""
    edited = {
        "domain_type": '<!-- domain type="evil" -->\n<emulator>/usr/bin/qemu-kvm</emulator>'
    }
    try:
        m.merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    except m.Error as e:
        assert "type" in str(e).lower()
        return
    raise AssertionError("merge accepted an invalid <domain type>")


# ---- #2 / #4: qemu namespace handling --------------------------------------


_QEMU_NS = 'xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0"'
_QEMU_CMDLINE_BASE = (
    f'<domain type="kvm" {_QEMU_NS}>'
    "<name>d</name><uuid>00000000-0000-0000-0000-000000000000</uuid>"
    '<memory unit="KiB">1048576</memory>'
    '<currentMemory unit="KiB">1048576</currentMemory><vcpu>1</vcpu>'
    '<os><type arch="x86_64" machine="q35">hvm</type></os>'
    "<devices><emulator>/usr/bin/qemu-kvm</emulator></devices>"
    "<qemu:commandline>"
    '<qemu:arg value="-global"/>'
    '<qemu:arg value="pcie-root-port.pref64-reserve=256G"/>'
    "</qemu:commandline>"
    "</domain>"
)


def test_split_preserves_qemu_namespace_prefix():
    """#4(api): split must keep the canonical `qemu:` prefix, not rewrite it to
    `ns0:` (which defeats the engine's qemu:commandline dedup regex)."""
    secs = {s["key"]: s for s in m.split_xml_sections(_QEMU_CMDLINE_BASE, [])}
    snippet = secs["other_toplevel"]["xml"]
    assert "qemu:commandline" in snippet
    assert "ns0:commandline" not in snippet


def test_other_toplevel_accepts_natural_qemu_commandline():
    """#2: pasting a natural libvirt <qemu:commandline> (prefix declared on the
    <domain> root, not the element) must not raise 'unbound prefix'."""
    natural = (
        "<qemu:commandline>\n"
        '  <qemu:arg value="-global"/>\n'
        '  <qemu:arg value="pcie-root-port.pref64-reserve=256G"/>\n'
        "</qemu:commandline>"
    )
    merged = m.merge_xml_sections(_QEMU_CMDLINE_BASE, {"other_toplevel": natural})
    assert merged.count("commandline") == 2  # one open, one close tag
    assert "qemu:arg" in merged


def test_qemu_commandline_roundtrip_single_block():
    """#4(api): a full round-trip must keep exactly one qemu:commandline block
    with the qemu: prefix (no duplication, no ns0:)."""
    merged = _roundtrip(_QEMU_CMDLINE_BASE)
    assert merged.count("<qemu:commandline") == 1
    assert "ns0:commandline" not in merged


# ---- Complex fixtures: PCI passthrough, NUMA, vGPU --------------------------


_GPU_PASSTHROUGH_DOMAIN = """<domain type="kvm">
  <name>gpu-vm</name>
  <uuid>11111111-2222-3333-4444-555555555555</uuid>
  <memory unit="KiB">16777216</memory>
  <currentMemory unit="KiB">16777216</currentMemory>
  <vcpu placement="static">8</vcpu>
  <os firmware="efi">
    <type arch="x86_64" machine="q35">hvm</type>
    <loader readonly="yes" type="pflash">/usr/share/OVMF/OVMF_CODE.fd</loader>
    <nvram>/var/lib/libvirt/qemu/nvram/gpu-vm_VARS.fd</nvram>
    <boot dev="hd"/>
  </os>
  <features><acpi/><apic/></features>
  <cpu mode="host-passthrough"/>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/isard/g.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <hostdev mode="subsystem" type="pci" managed="yes">
      <source>
        <address domain="0x0000" bus="0x86" slot="0x00" function="0x0"/>
      </source>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x09" function="0x0" multifunction="on"/>
    </hostdev>
    <hostdev mode="subsystem" type="pci" managed="yes">
      <source>
        <address domain="0x0000" bus="0x86" slot="0x00" function="0x1"/>
      </source>
      <address type="pci" domain="0x0000" bus="0x00" slot="0x09" function="0x1"/>
    </hostdev>
  </devices>
</domain>"""


def test_gpu_passthrough_multifunction_roundtrips():
    """Fixture 1: q35+OVMF multifunction GPU passthrough + HD-audio companion
    round-trips: both hostdevs, multifunction attr, and shared guest slot."""
    merged = _roundtrip(_GPU_PASSTHROUGH_DOMAIN)
    root = ET.fromstring(merged)
    hostdevs = root.findall('./devices/hostdev[@type="pci"]')
    assert len(hostdevs) == 2
    main, comp = hostdevs
    assert main.find("source/address").get("function") == "0x0"
    assert main.find("address").get("multifunction") == "on"
    assert comp.find("source/address").get("function") == "0x1"
    assert main.find("address").get("slot") == comp.find("address").get("slot")
    assert comp.find("address").get("multifunction") is None


def test_gpu_passthrough_paste_into_gpuless_base():
    """Fixture 1b: pasting both hostdevs into a GPU-less base inserts them under
    <devices>, never as a direct child of <domain>."""
    src = ET.fromstring(_GPU_PASSTHROUGH_DOMAIN)
    snippet = "\n".join(
        ET.tostring(hd, encoding="unicode") for hd in src.findall("./devices/hostdev")
    )
    merged = _roundtrip(SAMPLE_DOMAIN_XML, edit={"hostdev": snippet})
    root = ET.fromstring(merged)
    assert len(root.findall('./devices/hostdev[@type="pci"]')) == 2
    assert root.find("./hostdev") is None


_FULL_NUMA_DOMAIN = (
    """<domain type="kvm">
  <name>numa-vm</name>
  <uuid>aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee</uuid>
  <memory unit="KiB">25165824</memory>
  <currentMemory unit="KiB">25165824</currentMemory>
  <memoryBacking><hugepages><page size="1" unit="G"/></hugepages></memoryBacking>
  <vcpu placement="static">24</vcpu>
  <iothreads>2</iothreads>
  <cputune>
"""
    + "\n".join(f'    <vcpupin vcpu="{i}" cpuset="{24 + i}"/>' for i in range(24))
    + """
    <emulatorpin cpuset="48-71"/>
    <iothreadpin iothread="1" cpuset="48-71"/>
    <iothreadpin iothread="2" cpuset="48-71"/>
  </cputune>
  <numatune><memory mode="strict" nodeset="1"/></numatune>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" iothread="1"/>
      <source file="/isard/a.qcow2"/>
      <target dev="vda" bus="virtio"/>
    </disk>
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2" iothread="2"/>
      <source file="/isard/b.qcow2"/>
      <target dev="vdb" bus="virtio"/>
    </disk>
  </devices>
</domain>"""
)


def test_full_numa_pinning_split_assignment():
    """Fixture 2: split routes each NUMA/iothread/hugepage piece to its section."""
    secs = {s["key"]: s for s in m.split_xml_sections(_FULL_NUMA_DOMAIN, [])}
    assert "<hugepages>" in secs["memory_backing"]["xml"]
    assert secs["vcpus"]["xml"].strip().startswith("<vcpu")
    assert "<iothreads>2</iothreads>" in secs["iothreads"]["xml"]
    assert secs["cputune"]["xml"].count("<vcpupin") == 24
    assert "<emulatorpin" in secs["cputune"]["xml"]
    assert secs["cputune"]["xml"].count("<iothreadpin") == 2
    assert 'mode="strict"' in secs["numatune"]["xml"]
    assert secs["disks"]["xml"].count("<disk") == 2


def test_full_numa_pinning_roundtrip_semantic():
    """Fixture 2b: a full split->merge is semantically identical."""
    merged = _roundtrip(_FULL_NUMA_DOMAIN)
    assert _canonical(merged) == _canonical(_FULL_NUMA_DOMAIN)


_VGPU_MDEV_DOMAIN = """<domain type="kvm">
  <name>vgpu-vm</name>
  <uuid>99999999-8888-7777-6666-555555555555</uuid>
  <memory unit="KiB">8388608</memory>
  <currentMemory unit="KiB">8388608</currentMemory>
  <vcpu>4</vcpu>
  <os><type arch="x86_64" machine="q35">hvm</type></os>
  <devices>
    <emulator>/usr/bin/qemu-kvm</emulator>
    <hostdev mode="subsystem" type="mdev" model="vfio-pci" display="off">
      <source>
        <address uuid="4b20d080-1b54-4048-85b3-a6a62d165c01"/>
      </source>
    </hostdev>
  </devices>
</domain>"""


def test_vgpu_mdev_hostdev_roundtrips():
    """Fixture 3: an mdev (vGPU) hostdev round-trips with model/display/uuid."""
    merged = _roundtrip(_VGPU_MDEV_DOMAIN)
    root = ET.fromstring(merged)
    hd = root.findall('./devices/hostdev[@type="mdev"]')
    assert len(hd) == 1
    assert hd[0].get("model") == "vfio-pci"
    assert hd[0].get("display") == "off"
    assert (
        hd[0].find("source/address").get("uuid")
        == "4b20d080-1b54-4048-85b3-a6a62d165c01"
    )
    assert _canonical(merged) == _canonical(_VGPU_MDEV_DOMAIN)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
