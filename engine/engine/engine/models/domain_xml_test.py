from engine.models.domain_xml import DomainXML


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
