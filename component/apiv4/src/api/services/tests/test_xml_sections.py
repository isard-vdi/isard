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
