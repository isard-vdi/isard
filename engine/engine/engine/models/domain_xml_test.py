from io import StringIO

import pytest
from lxml import etree

import engine.models.domain_xml as dxml
from engine.models.domain_xml import (
    DomainXML,
    add_iothread_pinning,
    add_memory_backing,
    add_numa_pinning,
    add_qemu_pcie_reserve,
    count_passthrough_gpus_in_xml,
    domain_is_raw,
    ensure_iothreads_declared,
    hostdev_locked,
    numa_opts_allowed,
    pinned_cpuset_from_xml,
    recreate_xml_if_gpu,
    recreate_xml_to_start_raw,
    remove_memory_backing,
)


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


def test_remove_memory_backing_round_trip():
    """add_memory_backing then remove_memory_backing -> no <memoryBacking> (the
    native 4K shape), guest RAM untouched. This is the start-path OOM fallback."""
    xml = (
        '<domain type="kvm">'
        "<memory>16777216</memory>"
        "<currentMemory>16777216</currentMemory>"
        "<devices/>"
        "</domain>"
    )
    backed = add_memory_backing(xml, "1", "G")
    assert _parse(backed).xpath("/domain/memoryBacking/hugepages")  # sanity
    stripped = remove_memory_backing(backed)
    tree = _parse(stripped)
    assert tree.xpath("/domain/memoryBacking") == []  # whole element dropped
    assert tree.xpath("/domain/memory/text()")[0] == "16777216"  # RAM intact


def test_remove_memory_backing_keeps_virtiofs():
    """remove_memory_backing drops only hugepages/allocation/locked; a virtiofs
    <source>/<access> memoryBacking must survive (just without hugepages)."""
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
    backed = add_memory_backing(xml, "1", "G")  # adds hugepages alongside virtiofs
    stripped = remove_memory_backing(backed)
    tree = _parse(stripped)
    mb = tree.xpath("/domain/memoryBacking")
    assert len(mb) == 1  # kept (still has virtiofs children)
    assert mb[0].find("hugepages") is None and mb[0].find("locked") is None
    assert mb[0].find("source").get("type") == "memfd"
    assert mb[0].find("access").get("mode") == "shared"

    # virtiofs children still there
    assert mb[0].find("source") is not None
    assert mb[0].find("access") is not None


def test_remove_memory_backing_round_trip():
    """add_memory_backing then remove_memory_backing -> no <memoryBacking> (the
    native 4K shape), guest RAM untouched. This is the start-path OOM fallback."""
    xml = (
        '<domain type="kvm">'
        "<memory>16777216</memory>"
        "<currentMemory>16777216</currentMemory>"
        "<devices/>"
        "</domain>"
    )
    backed = add_memory_backing(xml, "1", "G")
    assert _parse(backed).xpath("/domain/memoryBacking/hugepages")  # sanity
    stripped = remove_memory_backing(backed)
    tree = _parse(stripped)
    assert tree.xpath("/domain/memoryBacking") == []  # whole element dropped
    assert tree.xpath("/domain/memory/text()")[0] == "16777216"  # RAM intact


def test_remove_memory_backing_keeps_virtiofs():
    """remove_memory_backing drops only hugepages/allocation/locked; a virtiofs
    <source>/<access> memoryBacking must survive (just without hugepages)."""
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
    backed = add_memory_backing(xml, "1", "G")  # adds hugepages alongside virtiofs
    stripped = remove_memory_backing(backed)
    tree = _parse(stripped)
    mb = tree.xpath("/domain/memoryBacking")
    assert len(mb) == 1  # kept (still has virtiofs children)
    assert mb[0].find("hugepages") is None  # but hugepages stripped
    assert mb[0].find("source").get("type") == "memfd"
    assert mb[0].find("access").get("mode") == "shared"


def test_set_memory_inserts_missing_currentmemory():
    """Regression: when <currentMemory> is absent, set_memory built the element
    with etree.parse() (an _ElementTree) and passed it to .addnext(), raising
    'expected _Element, got _ElementTree' and Failing the desktop on start. The
    .getroot() fix must insert <currentMemory> without raising."""
    xml = (
        '<domain type="kvm">'
        "<name>vm</name>"
        "<memory unit='KiB'>1048576</memory>"
        "<devices/>"
        "</domain>"
    )
    x = DomainXML(xml)
    x.set_memory(memory=1048576, unit="KiB", current=524288)
    tree = _parse(x.return_xml())
    assert tree.xpath("/domain/currentMemory/text()")[0] == "524288"


def test_set_memory_inserts_missing_memory_and_currentmemory():
    """Both <memory> and <currentMemory> absent: both are inserted after <name>
    without raising the lxml _ElementTree TypeError."""
    xml = '<domain type="kvm"><name>vm</name><devices/></domain>'
    x = DomainXML(xml)
    x.set_memory(memory=2097152, unit="KiB", current=1048576)
    tree = _parse(x.return_xml())
    assert tree.xpath("/domain/memory/text()")[0] == "2097152"
    assert tree.xpath("/domain/currentMemory/text()")[0] == "1048576"


def test_set_memory_maxmemory_inserts_before_memory():
    """maxMemory hotplug path: when <maxMemory> is absent the element must be
    inserted (it previously indexed the missing node -> IndexError) and ordered
    before <memory> per the libvirt schema."""
    xml = '<domain type="kvm"><name>vm</name><devices/></domain>'
    x = DomainXML(xml)
    x.set_memory(memory=1048576, unit="KiB", current=1048576, max=2097152)
    tree = _parse(x.return_xml())
    assert tree.xpath("/domain/maxMemory/text()")[0] == "2097152"
    order = [
        el.tag
        for el in tree.xpath("/domain/*")
        if el.tag in ("maxMemory", "memory", "currentMemory")
    ]
    assert order == ["maxMemory", "memory", "currentMemory"]


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


def test_recreate_xml_if_gpu_passthrough_single_function_deterministic_slot():
    """Compute-mode boards (no audio companion) now get a deterministic guest
    PCI slot from guest_index (default 0 -> 0x09), single function, NOT
    multifunction, so multi-GPU guests keep a stable carve-order-independent
    PCI layout."""
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
    guest_addr = hostdevs[0].find("address")
    assert guest_addr is not None
    assert guest_addr.get("slot") == "0x09"
    assert guest_addr.get("function") == "0x0"
    assert guest_addr.get("multifunction") is None


def test_recreate_xml_if_gpu_guest_index_distinct_slots():
    """Two GPUs on one desktop get distinct, index-derived guest slots
    (index 0 -> 0x09, index 1 -> 0x0a) regardless of which host card."""
    xml = '<domain type="kvm"><devices/></domain>'
    r0 = recreate_xml_if_gpu(
        xml, "u", pci_bus_id="pci_0000_03_00_0", is_passthrough=True, guest_index=0
    )
    r1 = recreate_xml_if_gpu(
        xml, "u", pci_bus_id="pci_0000_63_00_0", is_passthrough=True, guest_index=1
    )
    s0 = _parse(r0).xpath("//hostdev/address")[0].get("slot")
    s1 = _parse(r1).xpath("//hostdev/address")[0].get("slot")
    assert s0 == "0x09"
    assert s1 == "0x0a"
    assert s0 != s1


def test_recreate_xml_if_gpu_guest_index_deterministic_across_calls():
    """Same guest_index + same source card -> byte-identical XML (stable guest
    PCI address across starts)."""
    xml = '<domain type="kvm"><devices/></domain>'
    a = recreate_xml_if_gpu(
        xml, "u", pci_bus_id="pci_0000_03_00_0", is_passthrough=True, guest_index=2
    )
    b = recreate_xml_if_gpu(
        xml, "u", pci_bus_id="pci_0000_03_00_0", is_passthrough=True, guest_index=2
    )
    assert a == b
    assert _parse(a).xpath("//hostdev/address")[0].get("slot") == "0x0b"


def test_recreate_xml_if_gpu_companion_uses_guest_index_slot():
    """Companion multifunction pair lands on the index-derived slot (index 2 ->
    0x0b), .0 multifunction='on', .1 same slot at function 0x1."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(
        xml,
        "u",
        pci_bus_id="pci_0000_86_00_0",
        is_passthrough=True,
        companion_pci_bdfs=["0000:86:00.1"],
        guest_index=2,
    )
    hostdevs = _parse(result).xpath('//hostdev[@type="pci"][@managed="yes"]')
    assert len(hostdevs) == 2
    g0 = hostdevs[0].find("address")
    g1 = hostdevs[1].find("address")
    assert g0.get("slot") == "0x0b"
    assert g0.get("multifunction") == "on"
    assert g0.get("function") == "0x0"
    assert g1.get("slot") == "0x0b"
    assert g1.get("function") == "0x1"


def test_recreate_xml_if_gpu_guest_index_overflow_raises():
    """guest_index beyond the available guest PCI slots is a clear error, not a
    silently malformed address."""
    xml = '<domain type="kvm"><devices/></domain>'
    with pytest.raises(ValueError):
        recreate_xml_if_gpu(
            xml,
            "u",
            pci_bus_id="pci_0000_03_00_0",
            is_passthrough=True,
            guest_index=0x20,
        )


def test_recreate_xml_if_gpu_mig_mdev_sets_display_off():
    """A MIG-backed vGPU mdev (compute slice, no display engine) must emit
    display='off' on the hostdev; otherwise the guest fails to start."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(xml, "fake-uid", is_mig=True)
    tree = _parse(result)
    hd = tree.xpath('//hostdev[@type="mdev"]')
    assert len(hd) == 1
    assert hd[0].get("display") == "off"


def test_recreate_xml_if_gpu_plain_vgpu_mdev_keeps_default_display():
    """A plain (non-MIG) vGPU mdev keeps libvirt's default — no display
    attribute is injected (unchanged behaviour)."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(xml, "fake-uid")
    tree = _parse(result)
    hd = tree.xpath('//hostdev[@type="mdev"]')
    assert len(hd) == 1
    assert hd[0].get("display") is None


def test_recreate_xml_if_gpu_vfio_variant_vgpu_vf_hostdev():
    """On the vendor-specific VFIO framework (Ubuntu 24.04+) a vGPU is a vfio-pci
    passthrough of an SR-IOV VF with display='off', NOT an mdev hostdev. It must
    carry a 'ua-isard-vgpu-*' user alias so host-side reconcile can tell an
    engine-managed vGPU VF apart from a whole-card passthrough (both type='pci')."""
    xml = '<domain type="kvm"><devices/></domain>'
    result = recreate_xml_if_gpu(xml, "unused-uid", vgpu_vf_bdf="0000:05:00.4")
    tree = _parse(result)
    # vfio-pci VF passthrough, not an mdev
    assert tree.xpath('//hostdev[@type="mdev"]') == []
    # managed='no' is load-bearing: the VF stays nvidia-bound (the variant driver
    # is the VFIO provider); managed='yes' would unbind it and hang the host.
    hd = tree.xpath('//hostdev[@type="pci"][@managed="no"]')
    assert len(hd) == 1
    assert tree.xpath('//hostdev[@managed="yes"]') == []  # never managed for a vGPU VF
    assert hd[0].get("display") == "off"  # vGPU is headless on this path
    # source address points at the VF BDF 0000:05:00.4
    src = hd[0].xpath("./source/address")[0]
    assert src.get("domain") == "0x0000"
    assert src.get("bus") == "0x05"
    assert src.get("slot") == "0x00"
    assert src.get("function") == "0x4"
    # the load-bearing marker (libvirt user aliases must start with 'ua-')
    alias = hd[0].xpath("./alias")[0].get("name")
    assert alias.startswith("ua-isard-vgpu-")
    assert "0000-05-00-4" in alias


def test_remove_gpu_hostdev_strips_vfio_vgpu_by_alias_not_unrelated_managed_no():
    """Teardown must strip the managed='no' vfio vGPU VF hostdev via its
    'ua-isard-vgpu-*' alias marker, WITHOUT removing an unrelated managed='no'
    pci hostdev the desktop may carry."""
    base = '<domain type="kvm"><devices/></domain>'
    # engine-emitted vfio vGPU VF (managed='no' + alias marker)
    xml = recreate_xml_if_gpu(base, "u", vgpu_vf_bdf="0000:05:00.4")
    # splice in an UNRELATED managed='no' pci hostdev (no isard alias)
    x0 = DomainXML(xml)
    other = etree.fromstring(
        "<hostdev mode='subsystem' type='pci' managed='no'>"
        "<source><address domain='0x0000' bus='0x99' slot='0x00' function='0x0'/></source>"
        "<alias name='ua-user-other'/></hostdev>"
    )
    x0.tree.xpath("/domain/devices")[0].append(other)

    x = DomainXML(etree.tostring(x0.tree, encoding="unicode"))
    x.remove_gpu_hostdev()
    tree = x.tree
    # the engine vGPU VF (alias ua-isard-vgpu-*) is gone
    assert tree.xpath("//hostdev[starts-with(alias/@name,'ua-isard-vgpu-')]") == []
    # the unrelated managed='no' hostdev survives
    assert len(tree.xpath("//hostdev[alias/@name='ua-user-other']")) == 1


def test_recreate_xml_if_gpu_vfio_variant_rejects_malformed_vf_bdf():
    with pytest.raises(ValueError):
        recreate_xml_if_gpu(
            '<domain type="kvm"><devices/></domain>', "u", vgpu_vf_bdf="bad-bdf"
        )


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


def test_set_qos_disk_inserts_iotune_in_every_disk(monkeypatch):
    """set_qos_disk on a multi-disk domain must add <iotune> to every <disk>,
    not just the last. The previous code reused a single lxml element across
    the loop and `.addnext` *moves* a parented element, so disk 0 silently
    lost its iotune as soon as disk 1 was processed."""
    # ``engine.services.log`` is stubbed by ``engine/engine/conftest.py`` so
    # ``from engine.services.log import *`` doesn't bring ``log`` into
    # ``domain_xml``'s namespace under pytest. Inject a real logger only for
    # the duration of this test so the production ``log.debug(...)`` line
    # exercises without NameError.
    import logging

    from engine.models import domain_xml as _dx

    monkeypatch.setattr(_dx, "log", logging.getLogger(__name__), raising=False)
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


# ---- ensure_iothreads_declared: orphan <iothreadpin> repair on load ---------


def _iothreadpin_domain_xml(iothread_id="1", with_iothreads=None):
    """A domain with a <cputune><iothreadpin> referencing iothread_id. When
    with_iothreads is None no <iothreads> is declared (the orphan/bug shape);
    otherwise a <iothreads>{with_iothreads}</iothreads> is emitted after <vcpu>.
    """
    iothreads = (
        f"<iothreads>{with_iothreads}</iothreads>" if with_iothreads is not None else ""
    )
    return (
        '<domain type="kvm">'
        "<name>d1</name>"
        "<vcpu>24</vcpu>"
        f"{iothreads}"
        "<cputune>"
        '  <vcpupin vcpu="0" cpuset="48-71"/>'
        f'  <iothreadpin iothread="{iothread_id}" cpuset="92-93"/>'
        "</cputune>"
        "<devices/>"
        "</domain>"
    )


def test_ensure_iothreads_declared_inserts_missing():
    """Orphan <iothreadpin iothread='1'/> with no <iothreads> => declare
    <iothreads>1</iothreads> right after <vcpu> (the libvirt-correct order)."""
    result = ensure_iothreads_declared(_iothreadpin_domain_xml(iothread_id="1"))
    tree = _parse(result)
    iothreads = tree.xpath("/domain/iothreads")
    assert len(iothreads) == 1
    assert iothreads[0].text == "1"
    # Declared after <vcpu> and before <cputune>.
    children = [c.tag for c in tree.xpath("/domain")[0]]
    assert children.index("iothreads") == children.index("vcpu") + 1
    assert children.index("iothreads") < children.index("cputune")
    # Pinning preserved, not dropped.
    assert len(tree.xpath("/domain/cputune/iothreadpin")) == 1


def test_ensure_iothreads_declared_bumps_too_small():
    """<iothreads>1</iothreads> but a pin references iothread 3 => bump to 3."""
    result = ensure_iothreads_declared(
        _iothreadpin_domain_xml(iothread_id="3", with_iothreads="1")
    )
    tree = _parse(result)
    assert tree.xpath("/domain/iothreads")[0].text == "3"
    assert len(tree.xpath("/domain/iothreads")) == 1


def test_ensure_iothreads_declared_noop_when_already_covered():
    """A pin id already within <iothreads>N is left untouched (idempotent)."""
    xml = _iothreadpin_domain_xml(iothread_id="1", with_iothreads="2")
    result = ensure_iothreads_declared(xml)
    tree = _parse(result)
    assert tree.xpath("/domain/iothreads")[0].text == "2"


def test_ensure_iothreads_declared_noop_without_iothreadpin():
    """No <iothreadpin> => no <iothreads> synthesized, XML unchanged."""
    xml = (
        '<domain type="kvm"><name>d</name><vcpu>4</vcpu>'
        '<cputune><vcpupin vcpu="0" cpuset="0-3"/></cputune>'
        "<devices/></domain>"
    )
    result = ensure_iothreads_declared(xml)
    assert _parse(result).xpath("/domain/iothreads") == []


def test_ensure_iothreads_declared_honors_explicit_iothreadids():
    """An explicit <iothreadids><iothread id='5'/></iothreadids> already declares
    id 5 => a pin to 5 is a no-op (no spurious <iothreads> count added)."""
    xml = (
        '<domain type="kvm"><name>d</name><vcpu>8</vcpu>'
        '<iothreadids><iothread id="5"/></iothreadids>'
        '<cputune><iothreadpin iothread="5" cpuset="0-3"/></cputune>'
        "<devices/></domain>"
    )
    result = ensure_iothreads_declared(xml)
    tree = _parse(result)
    assert tree.xpath("/domain/iothreads") == []
    assert len(tree.xpath('/domain/iothreadids/iothread[@id="5"]')) == 1


# ---- pinned_cpuset_from_xml: NUMA-aware GPU placement input ----------------


def test_pinned_cpuset_from_xml_unions_vcpupin():
    """Union every <vcpupin cpuset/> into one cpulist string (the carve maps it
    to a NUMA node)."""
    xml = (
        '<domain type="kvm"><name>d</name><vcpu>24</vcpu>'
        '<cputune><vcpupin vcpu="0" cpuset="48-71"/>'
        '<vcpupin vcpu="1" cpuset="92-93"/>'
        '<iothreadpin iothread="1" cpuset="92-93"/></cputune>'
        "<devices/></domain>"
    )
    assert pinned_cpuset_from_xml(xml) == "48-71,92-93"


def test_pinned_cpuset_from_xml_reads_vcpu_attr():
    """A whole-domain <vcpu cpuset="..."> pin is also picked up."""
    xml = '<domain type="kvm"><vcpu cpuset="0-15">16</vcpu><devices/></domain>'
    assert pinned_cpuset_from_xml(xml) == "0-15"


def test_pinned_cpuset_from_xml_none_when_unpinned():
    """No pinning => None, so the carve keeps its default placement."""
    xml = '<domain type="kvm"><vcpu>4</vcpu><devices/></domain>'
    assert pinned_cpuset_from_xml(xml) is None


def test_pinned_cpuset_from_xml_none_on_bad_xml():
    """Malformed XML => None (never raises)."""
    assert pinned_cpuset_from_xml("<domain><not-closed>") is None


def test_count_passthrough_gpus_none():
    """No passthrough hostdevs => 0."""
    assert count_passthrough_gpus_in_xml("<domain><devices/></domain>") == 0


def test_count_passthrough_gpus_single():
    """One passed-through GPU => 1."""
    xml = recreate_xml_if_gpu(
        '<domain type="kvm"><devices/></domain>',
        "fake-uid",
        pci_bus_id="pci_0000_e7_00_0",
        is_passthrough=True,
    )
    assert count_passthrough_gpus_in_xml(xml) == 1


def test_count_passthrough_gpus_audio_companion_not_double_counted():
    """A GPU + its .1 audio companion is still ONE GPU (function 0x1 ignored)."""
    xml = recreate_xml_if_gpu(
        '<domain type="kvm"><devices/></domain>',
        "fake-uid",
        pci_bus_id="pci_0000_86_00_0",
        is_passthrough=True,
        companion_pci_bdfs=["0000:86:00.1"],
    )
    # two hostdevs (GPU + audio) but only one function-0 device => 1 GPU
    assert len(_parse(xml).xpath('//hostdev[@type="pci"][@managed="yes"]')) == 2
    assert count_passthrough_gpus_in_xml(xml) == 1


def test_count_passthrough_gpus_two_cards():
    """Two passed-through GPUs on distinct guest slots => 2 (the >=2 case that
    requires the pcie-root-port.pref64-reserve large-BAR window)."""
    xml = '<domain type="kvm"><devices/></domain>'
    xml = recreate_xml_if_gpu(
        xml, "uid-0", pci_bus_id="pci_0000_e7_00_0", is_passthrough=True, guest_index=0
    )
    xml = recreate_xml_if_gpu(
        xml, "uid-1", pci_bus_id="pci_0000_86_00_0", is_passthrough=True, guest_index=1
    )
    assert count_passthrough_gpus_in_xml(xml) == 2


def test_count_passthrough_gpus_bad_xml():
    """Malformed XML => 0 (never raises)."""
    assert count_passthrough_gpus_in_xml("<domain><not-closed>") == 0


def test_add_numa_pinning_excess_vcpus_still_pins_emulator():
    # More vCPUs (8) than the node has CPUs (0-3 = 4): per-vCPU pinning is
    # intentionally skipped to avoid core oversubscription, but the emulator
    # threads MUST still be pinned to the node and every vCPU constrained to it.
    xml = "<domain type='kvm'><vcpu placement='static'>8</vcpu><devices></devices></domain>"
    out = add_numa_pinning(xml, 0, "0-3", 8, emit_numatune=False)
    tree = etree.parse(StringIO(out))
    emu = tree.xpath("/domain/cputune/emulatorpin")
    assert emu and emu[0].get("cpuset") == "0-3"
    assert tree.xpath("/domain/vcpu")[0].get("cpuset") == "0-3"
    assert not tree.xpath(
        "/domain/cputune/vcpupin"
    )  # no per-vCPU pins when oversubscribed


def test_add_numa_pinning_fits_pins_all_vcpus_and_emulator():
    # 4 vCPUs on a 4-CPU node: full per-vCPU pinning + emulatorpin (regression lock).
    xml = "<domain type='kvm'><vcpu placement='static'>4</vcpu><devices></devices></domain>"
    out = add_numa_pinning(xml, 0, "0-3", 4, emit_numatune=False)
    tree = etree.parse(StringIO(out))
    assert len(tree.xpath("/domain/cputune/vcpupin")) == 4
    assert tree.xpath("/domain/cputune/emulatorpin")[0].get("cpuset") == "0-3"


# ---- B5: reset_mac_address off-by-one --------------------------------------


def test_reset_mac_address_targets_second_interface():
    """B5: reset_mac_address(dev_index=1) must set the SECOND interface's mac
    (an interface has exactly one <mac>), not raise IndexError."""
    xml = (
        '<domain type="kvm"><devices>'
        '<interface type="network"><source network="default"/>'
        '<mac address="52:54:00:00:00:01"/><model type="virtio"/></interface>'
        '<interface type="network"><source network="default"/>'
        '<mac address="52:54:00:00:00:02"/><model type="virtio"/></interface>'
        "</devices></domain>"
    )
    x = DomainXML(xml)
    x.reset_mac_address(dev_index=1, mac="52:54:00:ab:cd:ef")
    macs = _parse(x.return_xml()).xpath("/domain/devices/interface/mac")
    assert macs[0].get("address") == "52:54:00:00:00:01"
    assert macs[1].get("address") == "52:54:00:ab:cd:ef"


# ---- B6: dict_from_xml on a diskless + interfaceless domain -----------------


def test_dict_from_xml_diskless_interfaceless_domain():
    """B6: dict_from_xml must not raise UnboundLocalError ('tree') when the
    domain has no <disk device='disk'> and no <interface> (the boot_order
    comprehension used the loop variable instead of the document tree)."""
    xml = (
        '<domain type="kvm"><name>n</name><uuid>u</uuid>'
        "<memory>1048576</memory><vcpu>1</vcpu>"
        '<os><type arch="x86_64" machine="q35">hvm</type><boot dev="hd"/></os>'
        "<devices><emulator>/usr/bin/qemu-kvm</emulator></devices></domain>"
    )
    d = DomainXML(xml).dict_from_xml()
    assert d["boot_order"] == ["hd"]


# ---- NUMA / iothread pinning consistency (guards for B1 changes) -----------


def _numa_base_xml(vcpus=8):
    return (
        '<domain type="kvm">'
        "<memory>8388608</memory><currentMemory>8388608</currentMemory>"
        f'<vcpu placement="static">{vcpus}</vcpu>'
        "<devices><emulator>/usr/bin/qemu-kvm</emulator></devices></domain>"
    )


def _virtio_disks_domain(n):
    disks = "".join(
        '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        f'<source file="/isard/d{i}.qcow2"/>'
        f'<target dev="vd{chr(97 + i)}" bus="virtio"/></disk>'
        for i in range(n)
    )
    return (
        '<domain type="kvm">'
        "<memory>8388608</memory><currentMemory>8388608</currentMemory>"
        '<vcpu placement="static">8</vcpu>'
        f"<devices><emulator>/usr/bin/qemu-kvm</emulator>{disks}</devices></domain>"
    )


def test_add_numa_pinning_per_vcpu_when_fit():
    result = add_numa_pinning(_numa_base_xml(8), 1, "24-47", 8, "strict", True)
    tree = _parse(result)
    assert len(tree.xpath("/domain/cputune/vcpupin")) == 8
    # Each vCPU is pinned to the node's full CPU set, not a single CPU, so the
    # scheduler spreads same-node guests instead of stacking every guest on the
    # node's first N threads.
    assert all(
        p.get("cpuset") == "24-47" for p in tree.xpath("/domain/cputune/vcpupin")
    )
    assert len(tree.xpath("/domain/cputune/emulatorpin")) == 1
    nt = tree.xpath("/domain/numatune/memory")
    assert (
        len(nt) == 1 and nt[0].get("nodeset") == "1" and nt[0].get("mode") == "strict"
    )


def test_add_numa_pinning_cpuset_only_when_overcommit():
    result = add_numa_pinning(_numa_base_xml(24), 0, "0-3", 24, "preferred", True)
    tree = _parse(result)
    assert tree.xpath("/domain/cputune/vcpupin") == []
    assert tree.xpath("/domain/vcpu")[0].get("cpuset") == "0-3"


def test_add_iothread_pinning_three_disks():
    result = add_iothread_pinning(_virtio_disks_domain(3), "24-47")
    tree = _parse(result)
    io = tree.xpath("/domain/iothreads")
    assert len(io) == 1 and io[0].text == "3"
    pins = tree.xpath("/domain/cputune/iothreadpin")
    assert sorted(p.get("iothread") for p in pins) == ["1", "2", "3"]
    drivers = tree.xpath('/domain/devices/disk[@device="disk"]/driver')
    assert sorted(d.get("iothread") for d in drivers) == ["1", "2", "3"]


def test_add_iothread_pinning_no_orphan_iothreadpin():
    """Invariant from a prior production bug: every <iothreadpin> id must be
    <= the declared <iothreads> count (no orphan pin libvirt would reject)."""
    result = add_iothread_pinning(_virtio_disks_domain(2), "24-47")
    tree = _parse(result)
    count = int(tree.xpath("/domain/iothreads")[0].text)
    ids = [int(p.get("iothread")) for p in tree.xpath("/domain/cputune/iothreadpin")]
    assert ids and all(1 <= i <= count for i in ids)
    assert len(ids) == len(set(ids)) == count


def test_add_iothread_pinning_no_virtio_disks_unchanged():
    base = (
        '<domain type="kvm"><vcpu>4</vcpu><devices>'
        "<emulator>/usr/bin/qemu-kvm</emulator>"
        '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
        '<source file="/x.iso"/><target dev="sda" bus="sata"/></disk>'
        "</devices></domain>"
    )
    assert add_iothread_pinning(base, "0-3") == base


# ---- #4: qemu:commandline dedup must be namespace-prefix agnostic -----------


def test_add_qemu_pcie_reserve_dedups_ns0_prefixed_block():
    """#4: an editor-stored <ns0:commandline> block must be deduped, not left in
    place so a second <qemu:commandline> is appended (duplicate)."""
    xml = (
        '<domain xmlns:ns0="http://libvirt.org/schemas/domain/qemu/1.0" type="kvm">'
        "<name>d</name>"
        '<ns0:commandline><ns0:arg value="-global"/>'
        '<ns0:arg value="pcie-root-port.pref64-reserve=256G"/></ns0:commandline>'
        "</domain>"
    )
    result = add_qemu_pcie_reserve(xml, "256G")
    # exactly one commandline block survives (2 = one open + one close tag)
    assert result.count("commandline") == 2


# ---- B1: protected sections honored at engine start ------------------------


def test_add_numa_pinning_emit_cputune_false_preserves_existing_cputune():
    """B1: with emit_cputune=False a pre-existing (admin-protected) <cputune>
    must be left intact, while <numatune> can still be emitted independently."""
    base = _numa_base_xml(8).replace(
        "<devices>",
        "<cputune><vcpupin vcpu='0' cpuset='5'/></cputune><devices>",
    )
    result = add_numa_pinning(base, 1, "24-47", 8, "strict", True, emit_cputune=False)
    tree = _parse(result)
    pins = tree.xpath("/domain/cputune/vcpupin")
    assert len(pins) == 1 and pins[0].get("cpuset") == "5"  # untouched
    assert len(tree.xpath("/domain/numatune")) == 1  # numatune still emitted


def test_numa_opts_allowed_respects_protected_sections():
    """B1: a protected memory_backing/cputune/numatune/iothreads section must
    gate OFF the engine's start-time injection so it cannot overwrite the
    admin-locked XML."""
    d = {"create_dict": {"xml_protected_sections": ["memory_backing", "numatune"]}}
    allow = numa_opts_allowed(d)
    assert allow["memory_backing"] is False
    assert allow["numatune"] is False
    assert allow["cputune"] is True
    assert allow["iothreads"] is True


def test_numa_opts_allowed_default_when_nothing_protected():
    for d in (
        {"create_dict": {"xml_protected_sections": []}},
        {"create_dict": {"xml_protected_sections": None}},
        {"create_dict": {}},
        {"create_dict": None},
        {},
    ):
        assert all(numa_opts_allowed(d).values()), f"unexpected gate for {d!r}"


# ---- RAW XML mode ('raw' sentinel) -----------------------------------------


def test_domain_is_raw_and_locks_everything():
    raw = {"create_dict": {"xml_protected_sections": ["raw"]}}
    assert domain_is_raw(raw) is True
    assert domain_is_raw({"create_dict": {"xml_protected_sections": ["cpu"]}}) is False
    assert domain_is_raw({"create_dict": {}}) is False
    # 'raw' locks hostdev and disables every NUMA/hugepage/iothread injection.
    assert hostdev_locked(raw) is True
    assert all(v is False for v in numa_opts_allowed(raw).values())


_RAW_DOMAIN = (
    '<domain type="kvm">'
    "<name>placeholder</name>"
    '<memory unit="KiB">8388608</memory>'
    '<currentMemory unit="KiB">8388608</currentMemory>'
    '<vcpu placement="static">8</vcpu>'
    '<features><acpi/><apic/><kvm><hidden state="on"/></kvm></features>'
    '<os><type arch="x86_64" machine="q35">hvm</type><boot dev="hd"/></os>'
    '<cpu mode="host-passthrough"/>'
    "<devices>"
    "<emulator>/usr/bin/qemu-system-x86_64</emulator>"
    '<disk type="file" device="disk"><driver name="qemu" type="qcow2"/>'
    '<source file="/foreign/orig.qcow2"/><target dev="vda" bus="virtio"/></disk>'
    '<interface type="bridge"><source bridge="virbr0"/>'
    '<mac address="52:54:00:11:22:33"/><model type="virtio"/></interface>'
    '<video><model type="qxl"/></video>'
    "</devices>"
    '<qemu:commandline xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">'
    '<qemu:arg value="-cpu"/><qemu:arg value="host,+vmx"/>'
    "</qemu:commandline>"
    "</domain>"
)


def test_recreate_xml_to_start_raw_injects_essentials_keeps_the_rest(monkeypatch):
    dom_id = "11111111-2222-3333-4444-555555555555"
    dict_domain = {
        "id": dom_id,
        "user": "u",
        "group": "g",
        "category": "c",
        "create_dict": {
            "origin": "tpl",
            "xml_protected_sections": ["raw"],
            "hardware": {
                "disks": [{"storage_id": "s1"}],
                "interfaces": [{"id": "n1", "mac": "52:54:00:aa:bb:cc"}],
            },
        },
    }
    monkeypatch.setattr(
        dxml,
        "resolve_hardware_from_create_dict",
        lambda d: {"disks": [{"file": "/isard/managed/" + d["id"] + ".qcow2"}]},
    )

    def fake_ifaces(dd, x):
        # mimic isard networking: replace the interface + record a mac2network map
        for el in x.tree.xpath("/domain/devices/interface"):
            el.getparent().remove(el)
        ifc = etree.fromstring(
            '<interface type="bridge"><source bridge="ovs-br0"/>'
            '<mac address="52:54:00:aa:bb:cc"/><model type="virtio"/></interface>'
        )
        x.tree.xpath("/domain/devices")[0].append(ifc)
        x.mac2network_mappings = [
            {
                "mac": "52:54:00:aa:bb:cc",
                "kind": "interface",
                "interface_id": "n1",
                "vlan_id": "100",
            }
        ]

    monkeypatch.setattr(dxml, "recreate_xml_interfaces", fake_ifaces)

    x = DomainXML(_RAW_DOMAIN, id_domain=dom_id)
    out, passwd = recreate_xml_to_start_raw(dict_domain, x, ssl=True)
    t = _parse(out)

    # identity = desktop id
    assert t.xpath("/domain/name")[0].text == dom_id
    assert t.xpath("/domain/uuid")[0].text == dom_id
    # storage: isard-managed path injected, foreign path gone
    assert "/isard/managed/" in out and "/foreign/orig.qcow2" not in out
    # networking rebuilt + mac2network metadata emitted
    assert t.xpath('/domain/devices/interface/source[@bridge="ovs-br0"]')
    assert "mapping" in out and "52:54:00:aa:bb:cc" in out
    # viewer: spice + vnc + a fresh 32-char password
    assert t.xpath('/domain/devices/graphics[@type="spice"]')
    assert t.xpath('/domain/devices/graphics[@type="vnc"]')
    assert len(passwd) == 32
    # isard metadata injected
    assert t.xpath("/domain/metadata")
    # EVERYTHING ELSE preserved verbatim
    assert t.xpath("/domain/features/kvm/hidden")
    assert "host,+vmx" in out  # qemu:commandline untouched
    assert t.xpath("/domain/cpu")[0].get("mode") == "host-passthrough"
    assert t.xpath("/domain/memory")[0].text == "8388608"
    assert t.xpath("/domain/vcpu")[0].text == "8"
    assert t.xpath("/domain/devices/video/model")[0].get("type") == "qxl"


def test_dict_from_xml_disk_without_source_does_not_raise():
    # A disk may legitimately lack <source> before start: the engine injects it
    # from create_dict.hardware.disks (storage_id) at start time. dict_from_xml
    # is an info pass that must not crash on this state (regression: IndexError
    # on tree.xpath("source")[0] aborted every start of such a domain).
    xml = (
        '<domain type="kvm">'
        "<devices>"
        "<emulator>/usr/bin/qemu-kvm</emulator>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2"/>'
        '  <target dev="vda" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )
    x = DomainXML(xml)
    disks = x.vm_dict["disks"]
    assert len(disks) == 1
    assert disks[0].get("file") is None
    assert disks[0]["dev"] == "vda"
    assert disks[0]["bus"] == "virtio"
    assert disks[0]["type"] == "qcow2"


def test_set_vdisk_creates_missing_source():
    # A disk authored via the XML editor may have <driver>/<target> but no
    # <source>. set_vdisk injects the storage path at start time and must
    # create the <source> element when absent instead of indexing source[0]
    # (regression: IndexError in set_vdisk aborted the start).
    xml = (
        '<domain type="kvm">'
        "<devices>"
        "<emulator>/usr/bin/qemu-kvm</emulator>"
        '<disk type="file" device="disk">'
        '  <driver name="qemu" type="qcow2" cache="none"/>'
        '  <target dev="vda" bus="virtio"/>'
        "</disk>"
        "</devices>"
        "</domain>"
    )
    x = DomainXML(xml)
    path = x.set_vdisk("/isard/groups/new.qcow2", index=0, type_disk="qcow2")
    tree = _parse(x.return_xml())
    sources = tree.xpath('//disk[@device="disk"]/source')
    assert len(sources) == 1
    assert sources[0].get("file") == "/isard/groups/new.qcow2"
    assert path == "/isard/groups/new.qcow2"
    assert tree.xpath('//disk[@device="disk"]/driver')[0].get("type") == "qcow2"
