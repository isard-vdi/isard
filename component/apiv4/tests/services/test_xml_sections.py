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


# ---------------------------------------------------------------------------
# d0aa6c18e6 port: seven named sections plus the two catch-alls
# ---------------------------------------------------------------------------


_WIN11_MANUAL_DOMAIN = """<domain type="kvm">
  <name>win11</name>
  <memory unit="KiB">4194304</memory>
  <vcpu placement="static">2</vcpu>
  <os>
    <type arch="x86_64" machine="pc-q35-10.0">hvm</type>
    <loader readonly="yes" secure="no" type="pflash">/usr/share/OVMF/OVMF_CODE.fd</loader>
    <boot dev="hd"/>
  </os>
  <devices>
    <tpm model="tpm-tis">
      <backend type="emulator" version="2.0"/>
    </tpm>
    <audio id="1" type="spice"/>
    <serial type="pty"><target port="0"/></serial>
    <watchdog model="itco" action="reset"/>
  </devices>
</domain>"""


_NAMED_KEYS = {"tpm", "audio", "serial", "watchdog", "panic", "shmem", "iommu"}
_CATCHALL_KEYS = {"other_toplevel", "other_devices"}


def test_section_defs_includes_the_seven_named_sections():
    missing = _NAMED_KEYS - {s["key"] for s in SECTION_DEFS}
    assert not missing, f"SECTION_DEFS missing entries: {missing}"


def test_section_defs_includes_the_two_catchalls():
    missing = _CATCHALL_KEYS - {s["key"] for s in SECTION_DEFS}
    assert not missing, f"SECTION_DEFS missing catch-alls: {missing}"


def test_section_defs_keeps_the_apiv4_only_sections():
    """The reference lacks these ten; a wholesale replacement would drop them."""
    kept = {
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
    assert kept <= {s["key"] for s in SECTION_DEFS}


def test_ported_sections_are_protectable():
    """A non-protectable key renders a panel and then discards every edit."""
    for key in sorted(_NAMED_KEYS | _CATCHALL_KEYS):
        sdef = next(s for s in SECTION_DEFS if s["key"] == key)
        assert sdef["protectable"] is True, key


def test_ported_sections_are_not_derived():
    assert (_NAMED_KEYS | _CATCHALL_KEYS) & _DERIVED_KEYS == set()


@pytest.mark.parametrize("key", sorted(_NAMED_KEYS))
def test_section_allowed_tags_for_named_sections(key):
    sdef = next(s for s in SECTION_DEFS if s["key"] == key)
    assert _section_allowed_tags(sdef) == {key}


@pytest.mark.parametrize("key", sorted(_CATCHALL_KEYS))
def test_catchall_sections_accept_any_tag(key):
    sdef = next(s for s in SECTION_DEFS if s["key"] == key)
    assert sdef["xpaths"] == []
    assert _section_allowed_tags(sdef) is None


def test_serial_and_console_sections_do_not_claim_each_other():
    serial = next(s for s in SECTION_DEFS if s["key"] == "serial")
    console = next(s for s in SECTION_DEFS if s["key"] == "console")
    assert _section_allowed_tags(serial) == {"serial"}
    assert _section_allowed_tags(console) == {"console"}
    assert set(serial["xpaths"]).isdisjoint(console["xpaths"])


def test_audio_and_sound_sections_do_not_claim_each_other():
    audio = next(s for s in SECTION_DEFS if s["key"] == "audio")
    sound = next(s for s in SECTION_DEFS if s["key"] == "sound")
    assert set(audio["xpaths"]).isdisjoint(sound["xpaths"])


def test_split_manual_win11_xml_surfaces_the_tpm_section():
    sections = {s["key"]: s for s in split_xml_sections(_WIN11_MANUAL_DOMAIN, [])}
    tpm_xml = sections["tpm"]["xml"]
    assert '<tpm model="tpm-tis">' in tpm_xml
    assert '<backend type="emulator" version="2.0"' in tpm_xml


def test_split_manual_win11_xml_surfaces_audio_serial_and_watchdog():
    sections = {s["key"]: s for s in split_xml_sections(_WIN11_MANUAL_DOMAIN, [])}
    assert '<audio id="1" type="spice"' in sections["audio"]["xml"]
    assert '<serial type="pty">' in sections["serial"]["xml"]
    assert '<watchdog model="itco" action="reset"' in sections["watchdog"]["xml"]
    assert sections["console"]["xml"] == ""
    assert sections["sound"]["xml"] == ""


def test_split_surfaces_panic_shmem_and_iommu():
    base = _domain().replace(
        "</devices>",
        '<panic model="isa"/>'
        '<shmem name="ivshmem"><model type="ivshmem-plain"/></shmem>'
        '<iommu model="intel"/>'
        "</devices>",
    )
    sections = {s["key"]: s for s in split_xml_sections(base, [])}
    assert '<panic model="isa"' in sections["panic"]["xml"]
    assert '<shmem name="ivshmem">' in sections["shmem"]["xml"]
    assert '<iommu model="intel"' in sections["iommu"]["xml"]


def test_saving_the_tpm_section_keeps_it_in_the_full_xml():
    merged = _roundtrip(_WIN11_MANUAL_DOMAIN)
    root = ET.fromstring(merged)
    tpm = root.findall("./devices/tpm")
    assert len(tpm) == 1
    assert tpm[0].get("model") == "tpm-tis"
    assert tpm[0].find("backend").get("version") == "2.0"


def test_manual_win11_xml_roundtrips_unchanged():
    merged = _roundtrip(_WIN11_MANUAL_DOMAIN)
    assert _canonical(merged) == _canonical(_WIN11_MANUAL_DOMAIN)


def test_editing_the_tpm_section_changes_the_model():
    edit = '<tpm model="tpm-crb"><backend type="emulator" version="2.0"/></tpm>'
    merged = _roundtrip(_WIN11_MANUAL_DOMAIN, {"tpm": edit})
    assert ET.fromstring(merged).find("./devices/tpm").get("model") == "tpm-crb"


def test_merge_inserts_tpm_into_a_domain_that_has_none():
    snippet = '<tpm model="tpm-crb"><backend type="emulator" version="2.0"/></tpm>'
    merged = merge_xml_sections(_domain(), {"tpm": snippet})
    root = ET.fromstring(merged)
    assert root.find("./devices/tpm") is not None
    assert root.find("./tpm") is None


def test_merge_removes_the_tpm_on_an_empty_snippet():
    merged = merge_xml_sections(_WIN11_MANUAL_DOMAIN, {"tpm": ""})
    root = ET.fromstring(merged)
    assert root.find("./devices/tpm") is None
    assert root.find("./devices/watchdog") is not None


def test_merge_still_rejects_pasting_tpm_into_the_channels_section():
    with pytest.raises(Error) as exc:
        merge_xml_sections(_WIN11_MANUAL_DOMAIN, {"channels": "<tpm/>"})
    assert exc.value.status_code == 400


def test_merge_rejects_pasting_console_into_the_serial_section():
    with pytest.raises(Error) as exc:
        merge_xml_sections(_WIN11_MANUAL_DOMAIN, {"serial": '<console type="pty"/>'})
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# The catch-alls: the class of silent loss, not the seven known cases
# ---------------------------------------------------------------------------


_UNCLAIMED_TOPLEVEL = '<memtune><hard_limit unit="KiB">9437184</hard_limit></memtune>'
_UNCLAIMED_DEVICE = '<vsock model="virtio"><cid auto="no" address="3"/></vsock>'


def _domain_with_unclaimed():
    base = _domain(_UNCLAIMED_TOPLEVEL)
    return base.replace("</devices>", _UNCLAIMED_DEVICE + "</devices>")


def test_split_puts_an_unclaimed_toplevel_element_in_other_toplevel():
    sections = {s["key"]: s for s in split_xml_sections(_domain_with_unclaimed(), [])}
    assert "<memtune>" in sections["other_toplevel"]["xml"]


def test_split_puts_an_unclaimed_device_in_other_devices():
    sections = {s["key"]: s for s in split_xml_sections(_domain_with_unclaimed(), [])}
    assert "<vsock" in sections["other_devices"]["xml"]


def test_catchalls_do_not_duplicate_elements_a_named_section_already_claims():
    sections = {s["key"]: s for s in split_xml_sections(_domain_with_unclaimed(), [])}
    other_top = sections["other_toplevel"]["xml"]
    other_dev = sections["other_devices"]["xml"]
    for claimed in ("<name>", "<memory", "<os>", "<devices>"):
        assert claimed not in other_top
    assert "<disk" not in other_dev
    win11 = {s["key"]: s for s in split_xml_sections(_WIN11_MANUAL_DOMAIN, [])}
    assert win11["other_devices"]["xml"] == ""
    assert win11["other_toplevel"]["xml"] == ""


def _upload(uploaded_xml, target_xml):
    """The admin upload path: the uploaded file is split into sections, those
    fill the panels, and Save merges them into the target domain's xml."""
    sections = split_xml_sections(uploaded_xml, [])
    edited = {
        s["key"]: s["xml"] for s in sections if s["protectable"] and not s["derived"]
    }
    return merge_xml_sections(target_xml, edited)


def test_uploading_an_xml_carries_over_elements_no_named_section_claims():
    """The class, not the seven cases. Anything the panels do not cover never
    reaches the target domain, so uploading applies the file only in part."""
    merged = _upload(_domain_with_unclaimed(), _domain())
    root = ET.fromstring(merged)
    assert root.find("./memtune/hard_limit") is not None
    vsock = root.find("./devices/vsock")
    assert vsock is not None
    assert vsock.get("model") == "virtio"
    assert vsock.find("cid").get("address") == "3"


def test_an_element_no_named_section_claims_survives_split_save_split():
    base = _domain_with_unclaimed()
    merged = _roundtrip(base)
    root = ET.fromstring(merged)
    assert root.find("./memtune/hard_limit") is not None
    assert root.find("./devices/vsock") is not None
    again = {s["key"]: s for s in split_xml_sections(merged, [])}
    assert "<memtune>" in again["other_toplevel"]["xml"]
    assert "<vsock" in again["other_devices"]["xml"]


def test_catchall_merge_places_a_new_toplevel_element_in_libvirt_order():
    merged = merge_xml_sections(_domain(), {"other_toplevel": _UNCLAIMED_TOPLEVEL})
    tags = [c.tag for c in ET.fromstring(merged) if not callable(c.tag)]
    assert "memtune" in tags
    assert tags.index("memory") < tags.index("memtune") < tags.index("devices")


def test_catchall_roundtrip_preserves_comments_in_both_parents():
    base = (
        '<domain type="kvm">'
        "<!-- top comment -->"
        "<name>x</name>"
        "<uuid>11111111-1111-1111-1111-111111111111</uuid>"
        "<memory unit='KiB'>1048576</memory>"
        "<os><type arch='x86_64'>hvm</type></os>"
        "<devices>"
        "<!-- device comment -->"
        '<disk type="file" device="disk"><target dev="vda" bus="virtio"/></disk>'
        "</devices>"
        "</domain>"
    )
    merged = _roundtrip(base)
    assert "<!-- top comment -->" in merged
    assert "<!-- device comment -->" in merged


def test_editing_other_devices_replaces_only_the_unclaimed_devices():
    base = _domain_with_unclaimed()
    merged = _roundtrip(
        base, {"other_devices": '<vsock model="virtio-non-transitional"/>'}
    )
    root = ET.fromstring(merged)
    assert root.find("./devices/vsock").get("model") == "virtio-non-transitional"
    assert root.find('./devices/disk[@device="disk"]') is not None


def test_emptying_a_catchall_removes_its_unclaimed_elements():
    merged = merge_xml_sections(_domain_with_unclaimed(), {"other_devices": ""})
    root = ET.fromstring(merged)
    assert root.find("./devices/vsock") is None
    assert root.find('./devices/disk[@device="disk"]') is not None
    assert root.find("./memtune") is not None


def test_catchall_rejects_a_plain_text_snippet():
    with pytest.raises(Error) as exc:
        merge_xml_sections(_domain_with_unclaimed(), {"other_devices": "oops"})
    assert exc.value.status_code == 400


_CANONICAL_WITH_UNCLAIMED = """<domain type="kvm">
  <name>x</name>
  <uuid>11111111-1111-1111-1111-111111111111</uuid>
  <memory unit="KiB">1048576</memory>
  <memtune><hard_limit unit="KiB">9437184</hard_limit></memtune>
  <vcpu>2</vcpu>
  <os><type arch="x86_64">hvm</type></os>
  <devices>
    <disk type="file" device="disk"><target dev="vda" bus="virtio"/></disk>
    <vsock model="virtio"><cid auto="no" address="3"/></vsock>
    <graphics type="spice" port="-1"/>
  </devices>
</domain>"""


def test_catchall_noop_save_moves_nothing():
    """No pre-existing fixture has a non-empty catch-all, so without this the
    replace-in-place behaviour of _merge_catchall_section is untested."""
    merged = _roundtrip(_CANONICAL_WITH_UNCLAIMED)
    assert _canonical(merged) == _canonical(_CANONICAL_WITH_UNCLAIMED)
