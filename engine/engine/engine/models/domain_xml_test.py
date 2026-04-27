from io import StringIO

from engine.models.domain_xml import DomainXML, add_memory_backing, recreate_xml_if_gpu
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
