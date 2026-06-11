# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the XML sections editor service.

Pin the libvirt-element-order behaviour and the wrong-section-paste rejection
that ``60ad2b047`` added on main. The merge round-trip is exercised end-to-end
because reviewers and operators have learned to trust this layer with a
hand-edited XML.
"""

from xml.etree import ElementTree as ET

import pytest
from api.services.error import Error
from api.services.xml_sections import (
    _DERIVED_KEYS,
    LIBVIRT_DOMAIN_ORDER,
    SECTION_DEFS,
    _compute_derived_keys,
    _libvirt_toplevel_insert_index,
    _normalize_toplevel_order,
    _section_allowed_tags,
    _xpath_steps,
    merge_xml_sections,
    split_xml_sections,
)


def _domain(extra: str = "") -> str:
    """Minimal domain XML with name + memory + os + devices.

    Tests that exercise top-level-element insertion paste ``extra`` after
    <name>/<uuid> so the base document is well-formed for libvirt.
    """
    return (
        '<domain type="kvm">'
        "<name>x</name>"
        "<uuid>11111111-1111-1111-1111-111111111111</uuid>"
        f"{extra}"
        "<memory unit='KiB'>1048576</memory>"
        "<os><type arch='x86_64'>hvm</type></os>"
        "<devices>"
        '<disk type="file" device="disk">'
        '<driver name="qemu" type="qcow2"/>'
        '<source file="/a"/>'
        '<target dev="vda" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )


# ---------------------------------------------------------------------------
# SECTION_DEFS: the 10 new entries from 60ad2b047 are present.
# ---------------------------------------------------------------------------


def test_section_defs_includes_new_keys():
    keys = {s["key"] for s in SECTION_DEFS}
    expected = {
        "description",
        "max_memory",
        "memory_backing",
        "iothreads",
        "cputune",
        "numatune",
        "sysinfo",
        "resource",
        "lifecycle",
        "seclabel",
    }
    missing = expected - keys
    assert not missing, f"SECTION_DEFS missing 60ad2b047 entries: {missing}"


def test_lifecycle_section_xpaths_cover_all_three_lifecycle_tags():
    sdef = next(s for s in SECTION_DEFS if s["key"] == "lifecycle")
    assert sdef["xpaths"] == ["./on_poweroff", "./on_reboot", "./on_crash"]


# ---------------------------------------------------------------------------
# _section_allowed_tags
# ---------------------------------------------------------------------------


def test_section_allowed_tags_for_lifecycle_returns_three_tags():
    sdef = next(s for s in SECTION_DEFS if s["key"] == "lifecycle")
    assert _section_allowed_tags(sdef) == {"on_poweroff", "on_reboot", "on_crash"}


def test_section_allowed_tags_resolves_qemu_guest_agent_to_channel():
    sdef = next(s for s in SECTION_DEFS if s["key"] == "qemu_guest_agent")
    # xpath ends in `target[...]/..` — strip the predicate, follow `..` up one
    # level → "channel".
    assert _section_allowed_tags(sdef) == {"channel"}


def test_section_allowed_tags_seclabel():
    sdef = next(s for s in SECTION_DEFS if s["key"] == "seclabel")
    assert _section_allowed_tags(sdef) == {"seclabel"}


# ---------------------------------------------------------------------------
# _libvirt_toplevel_insert_index
# ---------------------------------------------------------------------------


def test_insert_index_for_memoryBacking_lands_before_devices():
    # name -> memory -> devices, want to insert memoryBacking between memory
    # and devices (canonical position).
    parent = ET.fromstring(
        "<domain>" "<name>x</name>" "<memory>1</memory>" "<devices/>" "</domain>"
    )
    idx = _libvirt_toplevel_insert_index(parent, "memoryBacking")
    # devices is at index 2; memoryBacking comes after memory, before devices.
    assert idx == 2


def test_insert_index_for_seclabel_lands_after_devices():
    parent = ET.fromstring(
        "<domain>" "<name>x</name>" "<memory>1</memory>" "<devices/>" "</domain>"
    )
    idx = _libvirt_toplevel_insert_index(parent, "seclabel")
    # seclabel comes after devices in LIBVIRT_DOMAIN_ORDER, so all known tags
    # come before it → append.
    assert idx == 3


def test_insert_index_unknown_tag_appends():
    parent = ET.fromstring("<domain><name>x</name></domain>")
    idx = _libvirt_toplevel_insert_index(parent, "totally_unknown")
    assert idx == 1


# ---------------------------------------------------------------------------
# _normalize_toplevel_order
# ---------------------------------------------------------------------------


def test_normalize_toplevel_order_heals_misplaced_seclabel():
    root = ET.fromstring(
        "<domain>"
        "<name>x</name>"
        "<seclabel/>"  # placed too early
        "<memory>1</memory>"
        "<devices/>"
        "</domain>"
    )
    _normalize_toplevel_order(root)
    tags = [c.tag for c in root]
    assert tags == ["name", "memory", "devices", "seclabel"]


def test_normalize_toplevel_order_idempotent_on_canonical_doc():
    root = ET.fromstring("<domain><name>x</name><memory>1</memory><devices/></domain>")
    before = [c.tag for c in root]
    _normalize_toplevel_order(root)
    after = [c.tag for c in root]
    assert before == after


def test_normalize_toplevel_order_unknown_tags_stay_after_known():
    root = ET.fromstring(
        "<domain>"
        "<custom_a/>"
        "<name>x</name>"
        "<custom_b/>"
        "<memory>1</memory>"
        "</domain>"
    )
    _normalize_toplevel_order(root)
    tags = [c.tag for c in root]
    # Known tags first in canonical order, unknown tags keep their relative
    # order at the end.
    assert tags == ["name", "memory", "custom_a", "custom_b"]


# ---------------------------------------------------------------------------
# merge_xml_sections — empty-section insertion at canonical position
# ---------------------------------------------------------------------------


def test_merge_inserts_memoryBacking_at_canonical_position_not_after_devices():
    """A domain that did NOT have <memoryBacking> gets one added via the
    editor. The new element must land between <memory> and <devices>, NOT
    after </devices> (libvirt rejects the latter)."""
    base = _domain()
    merged = merge_xml_sections(
        base,
        {"memory_backing": "<memoryBacking><hugepages/></memoryBacking>"},
    )
    root = ET.fromstring(merged)
    tags = [c.tag for c in root]
    assert "memoryBacking" in tags
    assert tags.index("memoryBacking") < tags.index(
        "devices"
    ), f"memoryBacking landed after devices: {tags}"


def test_merge_inserts_lifecycle_in_canonical_order():
    base = _domain()
    merged = merge_xml_sections(
        base,
        {
            "lifecycle": (
                "<on_poweroff>destroy</on_poweroff>"
                "<on_reboot>restart</on_reboot>"
                "<on_crash>destroy</on_crash>"
            )
        },
    )
    root = ET.fromstring(merged)
    tags = [c.tag for c in root]
    # All three lifecycle tags present.
    assert {"on_poweroff", "on_reboot", "on_crash"}.issubset(tags)
    # All three come AFTER memory/os and BEFORE devices in canonical order.
    devices_idx = tags.index("devices")
    for t in ("on_poweroff", "on_reboot", "on_crash"):
        assert tags.index(t) < devices_idx


def test_merge_normalizes_order_after_save():
    """A domain whose existing <seclabel> sits before <memory> (corrupt) is
    healed on a no-op edit save — no need to touch seclabel itself."""
    base = _domain('<seclabel type="dynamic"/>')
    # Use an empty edit to force a normalize pass.
    merged = merge_xml_sections(base, {"description": ""})
    root = ET.fromstring(merged)
    tags = [c.tag for c in root]
    assert tags.index("seclabel") > tags.index("devices")


# ---------------------------------------------------------------------------
# merge_xml_sections — wrong-section paste rejection
# ---------------------------------------------------------------------------


def test_merge_rejects_pasting_hostdev_into_redirdev_section():
    base = _domain()
    bad_paste = (
        '<hostdev mode="subsystem" type="pci">'
        '<source><address domain="0x0000" bus="0x01" slot="0x00" function="0x0"/></source>'
        "</hostdev>"
    )
    with pytest.raises(Error) as exc:
        merge_xml_sections(base, {"redirdev": bad_paste})
    assert exc.value.status_code == 400


def test_merge_accepts_correct_section_paste():
    base = _domain()
    # description section accepts <title> and <description>.
    ok_paste = "<title>my-vm</title><description>notes</description>"
    merged = merge_xml_sections(base, {"description": ok_paste})
    root = ET.fromstring(merged)
    assert root.find("./title") is not None
    assert root.find("./description") is not None


def test_merge_rejects_plain_text_snippet():
    """Plain text must fail loudly; silent accept would wipe existing elements."""
    base = _domain("<description>old notes</description>")
    with pytest.raises(Error) as exc:
        merge_xml_sections(base, {"description": "just plain text"})
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# split_xml_sections — surfaces the 10 new keys
# ---------------------------------------------------------------------------


def test_split_includes_new_keys_with_correct_xml():
    base = _domain(
        "<memoryBacking><hugepages/></memoryBacking>"
        "<numatune><memory mode='strict' nodeset='0'/></numatune>"
        "<seclabel type='dynamic'/>"
        "<on_poweroff>destroy</on_poweroff>"
        "<on_reboot>restart</on_reboot>"
        "<on_crash>destroy</on_crash>"
        "<title>my-vm</title>"
        "<description>notes</description>"
    )
    sections = {s["key"]: s for s in split_xml_sections(base, [])}
    assert "<memoryBacking>" in sections["memory_backing"]["xml"]
    assert "<numatune>" in sections["numatune"]["xml"]
    assert "<seclabel" in sections["seclabel"]["xml"]
    # Lifecycle section captures all three on_* elements.
    lifecycle_xml = sections["lifecycle"]["xml"]
    assert "<on_poweroff>" in lifecycle_xml
    assert "<on_reboot>" in lifecycle_xml
    assert "<on_crash>" in lifecycle_xml
    # Description section captures both title and description.
    desc_xml = sections["description"]["xml"]
    assert "<title>" in desc_xml
    assert "<description>" in desc_xml


# ---------------------------------------------------------------------------
# db8492ab2 — silent-edit-loss in XML sections editor
# ---------------------------------------------------------------------------


def test_xpath_steps_strips_predicates_and_anchor():
    assert _xpath_steps('.//devices/disk[@device="disk"]') == ["devices", "disk"]
    assert _xpath_steps("./os") == ["os"]
    # Trailing /.. resolves by popping the previous step.
    assert _xpath_steps('.//devices/channel[@type="unix"]/target[@name="ga"]/..') == [
        "devices",
        "channel",
    ]


def test_compute_derived_keys_resolves_disk_cache_and_qos_disk():
    """`disk_cache` and `qos_disk` xpaths sit inside `<disk>` elements owned by
    the `disks` / `isos` / `floppies` sections. They must be flagged derived."""
    derived = _compute_derived_keys()
    assert "disk_cache" in derived
    assert "qos_disk" in derived


def test_compute_derived_keys_does_not_flag_independent_sections():
    """`disks` / `isos` / `network` / `seclabel` etc. are NOT children of
    other sections — they must NOT be in the derived set."""
    derived = _compute_derived_keys()
    for key in ("disks", "isos", "network", "memory", "seclabel"):
        assert key not in derived


def test_split_marks_disk_cache_section_as_derived():
    base = _domain()
    sections = {s["key"]: s for s in split_xml_sections(base, [])}
    assert sections["disk_cache"]["derived"] is True
    assert sections["qos_disk"]["derived"] is True
    assert sections["disks"]["derived"] is False
    assert sections["seclabel"]["derived"] is False


def test_split_rejects_non_domain_root():
    """Uploading <foo>... is a partial fragment, not a libvirt domain. Without
    this guard the editor would silently render every section empty and the
    next save would wipe the textareas."""
    with pytest.raises(Error) as exc:
        split_xml_sections("<foo><bar/></foo>", [])
    assert exc.value.status_code == 400


def test_merge_ignores_stale_disk_cache_snippet_when_parent_edited():
    """Frontend posts every textarea on save. A stale `disk_cache` view sent
    alongside an edited `disks` parent must not silently revert the freshly
    merged <driver cache=...> back to the stale value."""
    base = _domain()
    edited_disks_xml = (
        '<disk type="file" device="disk">'
        '<driver name="qemu" type="qcow2" cache="writeback"/>'
        '<source file="/a"/>'
        '<target dev="vda" bus="virtio"/>'
        "</disk>"
    )
    stale_disk_cache = (
        '<driver name="qemu" type="qcow2"/>'  # no cache attr — stale view
    )
    merged = merge_xml_sections(
        base,
        {"disks": edited_disks_xml, "disk_cache": stale_disk_cache},
    )
    root = ET.fromstring(merged)
    drivers = root.findall(".//devices/disk/driver")
    assert len(drivers) == 1
    # The parent-section edit (cache=writeback) wins; the stale derived view
    # is ignored.
    assert drivers[0].get("cache") == "writeback"


def test_merge_ignores_stale_qos_disk_snippet_when_parent_edited():
    """Same contract as disk_cache: editing the parent disks section must
    win over a stale qos_disk derived view."""
    base = _domain()
    edited_disks_xml = (
        '<disk type="file" device="disk">'
        '<driver name="qemu" type="qcow2"/>'
        '<source file="/a"/>'
        '<target dev="vda" bus="virtio"/>'
        "<iotune><read_bytes_sec>2097152</read_bytes_sec></iotune>"
        "</disk>"
    )
    # Stale view with a different value — must not overwrite.
    stale_qos_disk = "<iotune><read_bytes_sec>1048576</read_bytes_sec></iotune>"
    merged = merge_xml_sections(
        base,
        {"disks": edited_disks_xml, "qos_disk": stale_qos_disk},
    )
    root = ET.fromstring(merged)
    iotune_vals = root.findall(".//devices/disk/iotune/read_bytes_sec")
    assert len(iotune_vals) == 1
    # The parent-section value wins.
    assert iotune_vals[0].text == "2097152"


def test_disk_cache_section_def_no_longer_carries_readonly_display():
    """The `readonly_display: True` flag on the `disk_cache` section was an
    unwired stub that 60ad2b047 / db8492ab2 replaced with the structural
    `_DERIVED_KEYS` computation. Make sure no contributor re-added it."""
    sdef = next(s for s in SECTION_DEFS if s["key"] == "disk_cache")
    assert "readonly_display" not in sdef


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
    sections = split_xml_sections(base_xml, [])
    edited = {s["key"]: s["xml"] for s in sections if s.get("protectable")}
    if edit:
        edited.update(edit)
    return merge_xml_sections(base_xml, edited)


# ---------------------------------------------------------------------------
# Upstream MR !4535 (xml-editor-live-libvirt-xml @ 5948ab8f0) additions:
# comment preservation, domain_type extra-attr round-trip, qemu namespace
# handling, GPU passthrough/mdev and NUMA-pinning round-trips.
# ---------------------------------------------------------------------------


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
    merged = merge_xml_sections(_NO_AGENT_BASE, {"qemu_guest_agent": snippet})
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
    merged = merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    assert ET.fromstring(merged).get("type") == "qemu"


def test_domain_type_rejects_invalid_type():
    """B4: an unknown domain type must be rejected, not silently applied."""
    edited = {
        "domain_type": '<!-- domain type="evil" -->\n<emulator>/usr/bin/qemu-kvm</emulator>'
    }
    try:
        merge_xml_sections(SAMPLE_DOMAIN_XML, edited)
    except Error as e:
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


def test_merge_preserves_qemu_namespace_prefix():
    """#4(api): a merge round-trip must keep the canonical `qemu:` prefix, not
    rewrite it to `ns0:` (which defeats the engine's qemu:commandline dedup
    regex). Upstream pins this on its catchall "other_toplevel" section; this
    branch's editor revision has no catchall sections, so the equivalent
    guarantee is that the un-split remainder round-trips with the registered
    prefix."""
    merged = _roundtrip(_QEMU_CMDLINE_BASE)
    assert "qemu:commandline" in merged
    assert "ns0:commandline" not in merged


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
    secs = {s["key"]: s for s in split_xml_sections(_FULL_NUMA_DOMAIN, [])}
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
