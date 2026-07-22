# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminDownloadsService._format_domains.

Two behaviours are locked in here:

1. ``disk_bus`` resolution: the upstream IsardVDI registry puts
   authoritative disk metadata in a sibling top-level ``hardware`` field,
   not inside ``create_dict.hardware.disks``. ``_format_domains`` copies
   ``bus`` across so the engine does not fall back to the hardcoded
   virtio default.
2. XML-driven protection hints: the engine overwrites ``<cpu>``,
   ``<interface>``, and ``<video>`` sections at start-time unless told
   otherwise. ``_format_domains`` inspects the registry XML and sets
   ``not_change_cpu_section`` + ``xml_protected_sections`` so older
   guests (TetrOS-style kvm32 + rtl8139) keep the drivers they shipped.
"""

from unittest.mock import patch

from api.services.admin.downloads import AdminDownloadsService

TETROS_XML = """
<domain type='kvm'>
  <name>tetros</name>
  <os><type arch='x86_64' machine='pc'>hvm</type></os>
  <cpu mode='custom' match='exact' check='partial'>
    <model fallback='allow'>kvm32</model>
  </cpu>
  <devices>
    <interface type='network'>
      <mac address='52:54:00:aa:bb:cc'/>
      <source network='default'/>
      <model type='rtl8139'/>
    </interface>
    <video>
      <model type='vga' vram='16384' heads='1' primary='yes'/>
    </video>
  </devices>
</domain>
""".strip()


def _registry_entry(cd_bus=None, top_bus=None, xml=None):
    """Build a registry entry shaped like the upstream /get/domains/list payload."""
    cd_disk = {"file": "x.qcow2", "parent": ""}
    if cd_bus is not None:
        cd_disk["bus"] = cd_bus

    entry = {
        "id": "downloaded_example",
        "name": "Example",
        "create_dict": {
            "hardware": {
                "boot_order": ["disk"],
                "disks": [cd_disk],
                "graphics": ["default"],
                "interfaces": ["default"],
                "memory": 1024,
                "vcpus": 1,
                "videos": ["vga"],
            },
            "hypervisors_pools": ["default"],
        },
        "url-isard": "example.qcow2",
    }
    if top_bus is not None:
        entry["hardware"] = {"disks": [{"bus": top_bus, "dev": "hda"}]}
    if xml is not None:
        entry["xml"] = xml
    return entry


def _run_format(entry):
    """Call _format_domains with the heavy external hooks stubbed out."""

    # _get_domain_if_already_downloaded: identity + pop as the real impl does,
    # so the test mirrors production where the top-level "hardware" field is
    # dropped by the time disk_bus resolution runs.
    def fake_already_downloaded(data, _user_id):
        for key in (
            "hardware",
            "xml_to_start",
            "hardware_from_xml",
            "force_update",
            "last_hyp_id",
        ):
            data.pop(key, None)
        return data

    with patch.object(
        AdminDownloadsService,
        "_get_domain_if_already_downloaded",
        side_effect=fake_already_downloaded,
    ), patch.object(
        AdminDownloadsService,
        "_get_user_data",
        return_value={
            "user": "u",
            "username": "u",
            "category": "c",
            "group": "g",
        },
    ), patch(
        "api.services.cards.CardService.get_domain_stock_card",
        return_value="stock.png",
    ), patch(
        "isardvdi_common.helpers.helpers.Helpers.gen_random_mac",
        return_value="52:54:00:00:00:01",
    ), patch(
        "isardvdi_common.helpers.isard_viewer.default_guest_properties",
        return_value={},
    ):
        return AdminDownloadsService._format_domains([entry], "user-id")[0]


class TestFormatDomainsDiskBus:
    def test_pulls_bus_from_sibling_hardware_when_create_dict_missing(self):
        """TetrOS-style entry: cd.hardware.disks[0] has no bus, sibling does."""
        entry = _registry_entry(cd_bus=None, top_bus="ide")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "ide"

    def test_create_dict_bus_wins_over_sibling(self):
        """If cd.hardware carries an explicit bus, prefer it over the sibling."""
        entry = _registry_entry(cd_bus="sata", top_bus="ide")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "sata"

    def test_no_disk_bus_key_when_both_sources_absent(self):
        """With neither source set, do not inject a disk_bus — let engine default."""
        entry = _registry_entry(cd_bus=None, top_bus=None)
        result = _run_format(entry)
        assert "disk_bus" not in result["create_dict"]["hardware"]

    def test_virtio_path_unchanged(self):
        """Debian/Ubuntu-style entry with virtio in both fields still lands on virtio."""
        entry = _registry_entry(cd_bus=None, top_bus="virtio")
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["disk_bus"] == "virtio"


class TestParseXmlProtectionHints:
    def test_tetros_xml_flags_all_three_sections(self):
        hints = AdminDownloadsService._parse_xml_protection_hints(TETROS_XML)
        assert hints["not_change_cpu_section"] is True
        assert set(hints["protected_sections"]) == {"cpu", "interface", "video"}

    def test_host_model_cpu_leaves_cpu_alone(self):
        """Host-model is exactly what the engine's override would install, so
        there is nothing to protect and the engine override is harmless."""
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-model'><model fallback='allow'/></cpu>"
            "<devices/>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert hints["not_change_cpu_section"] is False
        assert "cpu" not in hints["protected_sections"]

    def test_host_passthrough_cpu_leaves_cpu_alone(self):
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-passthrough'/>"
            "<devices/>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert hints["not_change_cpu_section"] is False
        assert "cpu" not in hints["protected_sections"]

    def test_interface_without_model_not_protected(self):
        xml = (
            "<domain type='kvm'>"
            "<devices>"
            "<interface type='network'><source network='default'/></interface>"
            "</devices>"
            "</domain>"
        )
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert "interface" not in hints["protected_sections"]

    def test_video_without_model_not_protected(self):
        xml = "<domain type='kvm'><devices><video/></devices></domain>"
        hints = AdminDownloadsService._parse_xml_protection_hints(xml)
        assert "video" not in hints["protected_sections"]

    def test_empty_xml_returns_empty_hints(self):
        hints = AdminDownloadsService._parse_xml_protection_hints("")
        assert hints == {"not_change_cpu_section": False, "protected_sections": []}

    def test_malformed_xml_does_not_raise(self):
        """Registry entries occasionally ship malformed/truncated XML; we
        must fall back to no hints instead of aborting the whole download."""
        hints = AdminDownloadsService._parse_xml_protection_hints("<domain><broken")
        assert hints == {"not_change_cpu_section": False, "protected_sections": []}


class TestFormatDomainsProtectionHints:
    def test_tetros_entry_sets_cpu_and_protection_list(self):
        """Full integration: TetrOS-shaped entry populates both engine gates."""
        entry = _registry_entry(cd_bus=None, top_bus="ide", xml=TETROS_XML)
        result = _run_format(entry)
        assert result["create_dict"]["hardware"]["not_change_cpu_section"] is True
        assert set(result["create_dict"]["xml_protected_sections"]) == {
            "cpu",
            "interface",
            "video",
        }

    def test_entry_without_xml_does_not_set_hints(self):
        """Debian-style entry with no registry xml leaves both fields absent
        so the engine keeps its current host-model + rebuild behaviour."""
        entry = _registry_entry(cd_bus=None, top_bus="virtio")
        result = _run_format(entry)
        assert "not_change_cpu_section" not in result["create_dict"]["hardware"]
        assert "xml_protected_sections" not in result["create_dict"]

    def test_host_model_xml_does_not_set_hints(self):
        """A modern guest with host-model CPU and no explicit NIC/video model
        should not opt in to protection — the engine's defaults are fine."""
        xml = (
            "<domain type='kvm'>"
            "<cpu mode='host-model'><model fallback='allow'/></cpu>"
            "<devices/>"
            "</domain>"
        )
        entry = _registry_entry(cd_bus=None, top_bus="virtio", xml=xml)
        result = _run_format(entry)
        assert "not_change_cpu_section" not in result["create_dict"]["hardware"]
        assert "xml_protected_sections" not in result["create_dict"]
