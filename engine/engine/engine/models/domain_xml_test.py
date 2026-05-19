from io import StringIO

import pytest
from engine.models.domain_xml import (
    DomainXML,
    add_memory_backing,
    hostdev_locked,
    recreate_xml_if_gpu,
)
from lxml import etree


def test_add_metadata_isard():
    cases = [
        {
            "in_xml": """<domain type="kvm"></domain>""",
            "expected_xml": """<domain type="kvm">
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:who user_id="user" group_id="group" category_id="category"/>
      <isard:parent parent_id="parent"/>
    </isard:isard>
  </metadata>
</domain>""",
        },
        {
            "in_xml": """<domain type="kvm">
    <metadata>
        <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
        <libosinfo:os id="http://debian.org/debian/10"/>
        </libosinfo:libosinfo>
    </metadata>
</domain>""",
            "expected_xml": """<domain type="kvm">
  <metadata>
    <libosinfo:libosinfo xmlns:libosinfo="http://libosinfo.org/xmlns/libvirt/domain/1.0">
      <libosinfo:os id="http://debian.org/debian/10"/>
    </libosinfo:libosinfo>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:who user_id="user" group_id="group" category_id="category"/>
      <isard:parent parent_id="parent"/>
    </isard:isard>
  </metadata>
</domain>""",
        },
    ]

    for c in cases:
        xml = DomainXML(c["in_xml"])
        xml.add_metadata_isard("user", "group", "category", "parent")
        assert xml.return_xml() == c["expected_xml"]


def test_qemu_guest_agent():
    cases = [
        {
            "in_xml": """
        <domain type="kvm">
            <devices></devices>
        </domain>
        """,
            "expected_xml": """<domain type="kvm">
  <devices>
    <channel type="unix">
      <source mode="bind"/>
      <target type="virtio" name="org.qemu.guest_agent.0"/>
    </channel>
  </devices>
</domain>""",
        },
        {
            "in_xml": """<domain type="kvm">
    <devices>
        <channel type="spicevmc">
            <target type="virtio" name="com.redhat.spice.0"/>
        </channel>
    </devices>
</domain>""",
            "expected_xml": """<domain type="kvm">
  <devices>
    <channel type="spicevmc">
      <target type="virtio" name="com.redhat.spice.0"/>
    </channel>
    <channel type="unix">
      <source mode="bind"/>
      <target type="virtio" name="org.qemu.guest_agent.0"/>
    </channel>
  </devices>
</domain>""",
        },
        {
            "in_xml": """<domain type="kvm">
    <devices>
        <channel type="unix">
            <source mode="bind"/>
            <target type="virtio" name="org.qemu.guest_agent.0"/>
        </channel>
        <channel type="spicevmc">
            <target type="virtio" name="com.redhat.spice.0"/>
        </channel>
    </devices>
</domain>""",
            "expected_xml": """<domain type="kvm">
  <devices>
    <channel type="unix">
      <source mode="bind"/>
      <target type="virtio" name="org.qemu.guest_agent.0"/>
    </channel>
    <channel type="spicevmc">
      <target type="virtio" name="com.redhat.spice.0"/>
    </channel>
  </devices>
</domain>""",
        },
    ]

    for c in cases:
        xml = DomainXML(c["in_xml"])
        xml.add_qemu_guest_agent()
        assert xml.return_xml() == c["expected_xml"]


def _parse(xml_str):
    """Helper: parse XML string into an lxml tree."""
    return etree.parse(StringIO(xml_str), etree.XMLParser(remove_blank_text=True))


def test_add_memory_backing_no_existing():
    """add_memory_backing creates memoryBacking when none exists."""
    xml = (
        '<domain type="kvm">'
        "<memory>8388608</memory>"
        "<currentMemory>8388608</currentMemory>"
        "<devices/>"
        "</domain>"
    )
    result = add_memory_backing(xml, "1", "G")
    tree = _parse(result)
    mb = tree.xpath("/domain/memoryBacking")
    assert len(mb) == 1
    assert mb[0].find("hugepages") is not None
    assert mb[0].find("hugepages/page").get("size") == "1"
    assert mb[0].find("allocation") is not None
    assert mb[0].find("locked") is not None


def test_add_memory_backing_preserves_virtiofs():
    """add_memory_backing must preserve <source type='memfd'/> and
    <access mode='shared'/> needed by virtiofs filesystems."""
    xml = (
        '<domain type="kvm">'
        "<memory>8388608</memory>"
        "<currentMemory>8388608</currentMemory>"
        "<devices>"
        '  <filesystem type="mount" accessmode="passthrough">'
        '    <driver type="virtiofs" queue="1024"/>'
        '    <source dir="/data"/>'
        '    <target dir="data"/>'
        "  </filesystem>"
        "</devices>"
        "<memoryBacking>"
        '  <source type="memfd"/>'
        '  <access mode="shared"/>'
        "</memoryBacking>"
        "</domain>"
    )
    result = add_memory_backing(xml, "1", "G")
    tree = _parse(result)
    mb = tree.xpath("/domain/memoryBacking")
    assert len(mb) == 1

    # Hugepages added
    assert mb[0].find("hugepages") is not None
    assert mb[0].find("allocation") is not None
    assert mb[0].find("locked") is not None

    # virtiofs children preserved
    source = mb[0].find("source")
    assert source is not None, "memoryBacking <source> lost"
    assert source.get("type") == "memfd"
    access = mb[0].find("access")
    assert access is not None, "memoryBacking <access> lost"
    assert access.get("mode") == "shared"


def test_add_memory_backing_idempotent():
    """Calling add_memory_backing twice replaces hugepages, keeps virtiofs."""
    xml = (
        '<domain type="kvm">'
        "<memory>8388608</memory>"
        "<currentMemory>8388608</currentMemory>"
        "<memoryBacking>"
        '  <source type="memfd"/>'
        '  <access mode="shared"/>'
        "</memoryBacking>"
        "<devices/>"
        "</domain>"
    )
    result = add_memory_backing(xml, "1", "G")
    result = add_memory_backing(result, "2", "M")
    tree = _parse(result)
    mb = tree.xpath("/domain/memoryBacking")
    assert len(mb) == 1

    # Only one hugepages block (the 2M one)
    hp = mb[0].findall("hugepages")
    assert len(hp) == 1
    assert hp[0].find("page").get("size") == "2"
    assert hp[0].find("page").get("unit") == "M"

    # virtiofs children still there
    assert mb[0].find("source") is not None
    assert mb[0].find("access") is not None


def test_recreate_xml_if_gpu_preserves_channel():
    """GPU passthrough injection must not corrupt guest agent channel."""
    xml = (
        '<domain type="kvm">'
        "<devices>"
        '<channel type="unix">'
        '  <source mode="bind"/>'
        '  <target type="virtio" name="org.qemu.guest_agent.0"/>'
        "</channel>"
        '<channel type="spicevmc">'
        '  <target type="virtio" name="com.redhat.spice.0"/>'
        "</channel>"
        '<filesystem type="mount" accessmode="passthrough">'
        '  <driver type="virtiofs" queue="1024"/>'
        '  <source dir="/data"/>'
        '  <target dir="data"/>'
        "</filesystem>"
        "</devices>"
        "<memoryBacking>"
        '  <source type="memfd"/>'
        '  <access mode="shared"/>'
        "</memoryBacking>"
        "</domain>"
    )
    result = recreate_xml_if_gpu(
        xml, "fake-uid", pci_bus_id="pci_0000_01_00_0", is_passthrough=True
    )
    tree = _parse(result)

    # Channel preserved with both children
    ga = tree.xpath('//channel[@type="unix"]/target[@name="org.qemu.guest_agent.0"]')
    assert len(ga) == 1, "guest agent target missing"
    ga_src = tree.xpath('//channel[@type="unix"]/source[@mode="bind"]')
    assert len(ga_src) == 1, "guest agent source missing"

    # GPU hostdev added
    hd = tree.xpath('//hostdev[@type="pci"][@managed="yes"]')
    assert len(hd) == 1

    # filesystem preserved
    assert len(tree.xpath("//filesystem")) == 1


def test_recreate_xml_if_gpu_passthrough_with_audio_companion():
    """Display-mode NVIDIA boards must emit GPU + .1 audio as a multifunction
    pair on a single guest PCI slot, matching bare-metal topology so the GPU
    driver finds its HDMI/DP audio codec at the expected offset."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(
        xml,
        "fake-uid",
        pci_bus_id="pci_0000_86_00_0",
        is_passthrough=True,
        companion_pci_bdfs=["0000:86:00.1"],
    )
    tree = _parse(result)

    hostdevs = tree.xpath('//hostdev[@type="pci"][@managed="yes"]')
    assert len(hostdevs) == 2, "expected one hostdev for .0 + one for .1"

    # Main function: source 86:00.0, guest-side multifunction='on'
    main = hostdevs[0]
    main_src = main.find("source/address")
    assert main_src.get("bus") == "0x86"
    assert main_src.get("slot") == "0x00"
    assert main_src.get("function") == "0x0"
    main_guest = main.find("address")
    assert main_guest.get("multifunction") == "on"
    assert main_guest.get("function") == "0x0"
    main_guest_slot = main_guest.get("slot")

    # Companion: source 86:00.1, same guest slot at function 0x1
    companion = hostdevs[1]
    comp_src = companion.find("source/address")
    assert comp_src.get("bus") == "0x86"
    assert comp_src.get("slot") == "0x00"
    assert comp_src.get("function") == "0x1"
    comp_guest = companion.find("address")
    assert comp_guest.get("slot") == main_guest_slot
    assert comp_guest.get("function") == "0x1"
    # Companion is not the first function — must NOT carry multifunction
    assert comp_guest.get("multifunction") is None


def test_recreate_xml_if_gpu_passthrough_without_companion_unchanged():
    """Compute-mode boards (no audio companion) keep the original
    single-hostdev shape with no guest-side address (libvirt auto-assigns)."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(
        xml,
        "fake-uid",
        pci_bus_id="pci_0000_c1_00_0",
        is_passthrough=True,
        companion_pci_bdfs=[],
    )
    tree = _parse(result)
    hostdevs = tree.xpath('//hostdev[@type="pci"][@managed="yes"]')
    assert len(hostdevs) == 1
    # No guest-side multifunction injection when there are no companions.
    guest_addr = hostdevs[0].find("address")
    assert guest_addr is None


# ---- engine bug fixes surfaced during the Redmine #15065 audit -------------


def _two_disk_domain_xml():
    return (
        '<domain type="kvm">'
        "<devices>"
        "<emulator>/usr/bin/qemu-kvm</emulator>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <source file="/var/isard/a.qcow2"/>'
        '  <target dev="vda" bus="virtio"/>'
        "</disk>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <source file="/var/isard/b.qcow2"/>'
        '  <target dev="vdb" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )


def test_set_qos_disk_inserts_iotune_in_every_disk():
    """set_qos_disk on a multi-disk domain must add <iotune> to every <disk>,
    not just the last. The previous code reused a single lxml element across
    the loop and `.addnext` *moves* a parented element, so disk 0 silently
    lost its iotune as soon as disk 1 was processed."""
    x = DomainXML(_two_disk_domain_xml())
    x.set_qos_disk(
        {
            "read_bytes_sec": 1048576,
            "write_iops_sec": 200,
        }
    )
    tree = _parse(x.return_xml())
    iotunes = tree.xpath('//disk[@device="disk"]/iotune')
    assert (
        len(iotunes) == 2
    ), f"expected one <iotune> per disk on a 2-disk domain; got {len(iotunes)}"
    for io in iotunes:
        assert io.find("read_bytes_sec") is not None
        assert io.find("read_bytes_sec").text == "1048576"
        assert io.find("write_iops_sec") is not None
        assert io.find("write_iops_sec").text == "200"


def test_set_qos_disk_skips_zero_and_non_int_values():
    """No <iotune> is added if every value is 0 / non-int — the iotune element
    would be empty and libvirt rejects empty <iotune>."""
    x = DomainXML(_two_disk_domain_xml())
    x.set_qos_disk({"read_bytes_sec": 0, "write_iops_sec": "ignore-strings"})
    tree = _parse(x.return_xml())
    assert tree.xpath('//disk[@device="disk"]/iotune') == []


def test_set_vdisk_does_not_apply_cache_attribute(monkeypatch):
    """set_vdisk used to call self.set_disk_driver_cache() inline, which
    bypassed the top-level `disk_cache not in protected` guard in
    recreate_xml_to_start. Removing the inline call means changing a disk
    path no longer silently overrides an admin's locked cache setting."""
    monkeypatch.setenv("ENGINE_GUESTS_DISK_DRIVER_CACHE", "writeback")
    xml = (
        '<domain type="kvm">'
        "<devices>"
        "<emulator>/usr/bin/qemu-kvm</emulator>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <source file="/var/isard/old.qcow2"/>'
        '  <target dev="vda" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )
    x = DomainXML(xml)
    x.set_vdisk("/var/isard/new.qcow2", index=0, type_disk="qcow2")
    tree = _parse(x.return_xml())
    driver = tree.xpath('//disk[@device="disk"]/driver')[0]
    # cache must not have been silently set by set_vdisk's side effect.
    assert driver.get("cache") is None, (
        "set_vdisk silently set cache attribute; admin disk_cache lock would "
        "be bypassed on path migration"
    )
    # path/type changes still apply
    assert (
        tree.xpath('//disk[@device="disk"]/source')[0].get("file")
        == "/var/isard/new.qcow2"
    )
    assert driver.get("type") == "qcow2"


def test_set_disk_driver_cache_top_level_still_applies():
    """Top-level set_disk_driver_cache (the legitimate apply path used by
    recreate_xml_to_start when disk_cache is NOT protected) still mutates
    every disk's <driver cache=…/> as before — the set_vdisk-inline-call
    removal must not have broken the canonical path."""
    xml = (
        '<domain type="kvm">'
        "<devices>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <source file="/a.qcow2"/>'
        '  <target dev="vda" bus="virtio"/>'
        "</disk>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <source file="/b.qcow2"/>'
        '  <target dev="vdb" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )
    import os

    prev = os.environ.get("ENGINE_GUESTS_DISK_DRIVER_CACHE")
    os.environ["ENGINE_GUESTS_DISK_DRIVER_CACHE"] = "writeback"
    try:
        x = DomainXML(xml)
        x.set_disk_driver_cache()
        tree = _parse(x.return_xml())
        drivers = tree.xpath('//disk[@device="disk"]/driver')
        assert len(drivers) == 2
        assert all(d.get("cache") == "writeback" for d in drivers)
    finally:
        if prev is None:
            del os.environ["ENGINE_GUESTS_DISK_DRIVER_CACHE"]
        else:
            os.environ["ENGINE_GUESTS_DISK_DRIVER_CACHE"] = prev


# ---- XML-edit GPU/hostdev robustness fixes (#6-#9) -------------------------


def test_hostdev_locked_true_when_section_protected():
    """#6: hostdev_locked is True iff create_dict.xml_protected_sections
    contains 'hostdev' — the signal that managed GPU reservation/injection
    must be skipped because the manual passthrough <hostdev> is authoritative."""
    assert hostdev_locked(
        {"create_dict": {"xml_protected_sections": ["memory", "hostdev"]}}
    )


def test_hostdev_locked_false_variants():
    """#6: anything that is not an explicit 'hostdev' lock yields False:
    other sections, empty/None list, missing create_dict, empty doc."""
    assert not hostdev_locked({"create_dict": {"xml_protected_sections": ["memory"]}})
    assert not hostdev_locked({"create_dict": {"xml_protected_sections": []}})
    assert not hostdev_locked({"create_dict": {"xml_protected_sections": None}})
    assert not hostdev_locked({"create_dict": {}})
    assert not hostdev_locked({"create_dict": None})
    assert not hostdev_locked({})


def test_recreate_xml_if_gpu_raises_clear_error_on_invalid_xml():
    """#7: a parse failure raises a clear ValueError instead of falling
    through to an unbound `tree` and surfacing as a confusing
    NameError/UnboundLocalError that masks the real cause."""
    with pytest.raises(ValueError, match="invalid domain XML"):
        recreate_xml_if_gpu("<domain><not-closed>", "fake-uid")


def test_recreate_xml_if_gpu_rejects_malformed_pci_bus_id():
    """#8: a malformed pci_bus_id raises a clear ValueError naming the
    offending value, instead of an opaque IndexError from split('_')."""
    xml = '<domain type="kvm"><devices/></domain>'
    with pytest.raises(ValueError, match="pci_bus_id"):
        recreate_xml_if_gpu(
            xml, "fake-uid", pci_bus_id="not-a-bdf", is_passthrough=True
        )


def test_recreate_xml_if_gpu_valid_pci_bus_id_address():
    """#8: a well-formed pci_bus_id still yields the correct <hostdev pci>
    source address (regression guard for the new validation gate)."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(
        xml, "fake-uid", pci_bus_id="pci_0000_21_00_0", is_passthrough=True
    )
    tree = _parse(result)
    addr = tree.xpath('//hostdev[@type="pci"]/source/address')
    assert len(addr) == 1
    assert addr[0].get("domain") == "0x0000"
    assert addr[0].get("bus") == "0x21"
    assert addr[0].get("slot") == "0x00"
    assert addr[0].get("function") == "0x0"


def test_remove_device_emits_no_stdout(capsys):
    """#9: remove_device must not print debug noise ('ORDER NUM:' /
    'REMAINING:') on the hot start path, while still removing every match."""
    x = DomainXML(
        '<domain type="kvm"><devices>'
        "<hostdev mode='subsystem' type='pci'><source/></hostdev>"
        "<hostdev mode='subsystem' type='pci'><source/></hostdev>"
        "</devices></domain>"
    )
    assert x.remove_device("/domain/devices/hostdev", order_num=-1) is True
    tree = _parse(x.return_xml())
    assert tree.xpath("//hostdev") == []
    captured = capsys.readouterr()
    assert captured.out == ""


def _devices_domain_xml():
    return '<domain type="kvm"><devices></devices></domain>'


@pytest.mark.parametrize(
    "type_interface, net, expect_mtu",
    [
        ("ovs", "100", True),  # default OVS/GENEVE tenant overlay
        ("ovs1", "100", True),  # custom ovsbr1 overlay
        ("network", "default", False),  # NAT default — rides underlay
        ("bridge", "default", False),  # n2m-bridge — rides underlay
    ],
)
def test_add_interface_overlay_gets_virtio_mtu(
    monkeypatch, type_interface, net, expect_mtu
):
    monkeypatch.setattr(
        "engine.models.domain_xml.get_cluster_guest_mtu_cached", lambda: 1386
    )
    x = DomainXML(_devices_domain_xml())
    x.add_interface(type_interface, "52:54:00:aa:bb:cc", "dom1", "if1", net=net)
    mtus = _parse(x.return_xml()).xpath("/domain/devices/interface/mtu")
    if expect_mtu:
        assert len(mtus) == 1 and mtus[0].get("size") == "1386"
    else:
        assert mtus == []


def test_add_interface_overlay_no_mtu_when_cluster_value_none(monkeypatch):
    """None => XML unchanged (no <mtu>), interface still added: zero regression
    on older/mixed/fresh clusters that do not publish vpn.guest_mtu yet."""
    monkeypatch.setattr(
        "engine.models.domain_xml.get_cluster_guest_mtu_cached", lambda: None
    )
    x = DomainXML(_devices_domain_xml())
    x.add_interface("ovs", "52:54:00:aa:bb:cc", "dom1", "if1", net="100")
    tree = _parse(x.return_xml())
    assert tree.xpath("/domain/devices/interface/mtu") == []
    assert len(tree.xpath("/domain/devices/interface")) == 1
