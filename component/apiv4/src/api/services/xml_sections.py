# XML sections editor service
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
import traceback
import uuid
from xml.etree import ElementTree as ET

from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.xml_sections import XmlSectionsProcessed

# Maximum size for a single XML snippet (256 KB)
MAX_SNIPPET_SIZE = 256 * 1024


def _safe_fromstring(xml_str: str) -> ET.Element:
    """Parse XML string with protection against entity expansion (Billion Laughs).

    Python's xml.etree.ElementTree uses expat which does NOT resolve external
    entities (SYSTEM/PUBLIC), but DOES expand internal entities without limit.
    We reject any XML containing a DOCTYPE declaration to prevent entity bombs.
    """
    stripped = xml_str.strip()
    if "<!DOCTYPE" in stripped or "<!ENTITY" in stripped:
        raise Error(
            "bad_request",
            "XML DOCTYPE and ENTITY declarations are not allowed",
            traceback.format_exc(),
        )
    return ET.fromstring(stripped)


# Canonical libvirt direct-children-of-<domain> order. Used to compute the
# correct insertion index when a section is empty in the base XML and the user
# adds it via the editor. See `_libvirt_toplevel_insert_index`.
# Reference: https://libvirt.org/formatdomain.html
LIBVIRT_DOMAIN_ORDER = [
    "name",
    "uuid",
    "genid",
    "title",
    "description",
    "metadata",
    "maxMemory",
    "memory",
    "currentMemory",
    "memoryBacking",
    "memtune",
    "vcpu",
    "vcpus",
    "iothreads",
    "iothreadids",
    "cputune",
    "numatune",
    "resource",
    "sysinfo",
    "bootloader",
    "os",
    "features",
    "cpu",
    "clock",
    "on_poweroff",
    "on_reboot",
    "on_crash",
    "pm",
    "perf",
    "idmap",
    "devices",
    "seclabel",
    "keywrap",
]


# Section definitions: key -> (label, group, xpaths, protectable)
# "group" is used by the frontend to build the grouped nav menu.
# xpaths is a list of XPath expressions to extract from the XML.
# For device sections that can have multiple elements, we use findall.
SECTION_DEFS = [
    # --- Identity (always engine-managed) ---
    {
        "key": "identity",
        "label": "Identity",
        "group": "System",
        "xpaths": ["./name", "./uuid"],
        "protectable": False,
    },
    {
        "key": "description",
        "label": "Title / Description",
        "group": "System",
        "xpaths": ["./title", "./description"],
        "protectable": True,
    },
    # --- Compute ---
    {
        "key": "memory",
        "label": "Memory",
        "group": "Compute",
        "xpaths": ["./memory", "./currentMemory"],
        "protectable": True,
    },
    {
        "key": "max_memory",
        "label": "Max Memory (hot-plug)",
        "group": "Compute",
        "xpaths": ["./maxMemory"],
        "protectable": True,
    },
    {
        "key": "memory_backing",
        "label": "Memory Backing",
        "group": "Compute",
        "xpaths": ["./memoryBacking"],
        "protectable": True,
    },
    {
        "key": "vcpus",
        "label": "vCPUs",
        "group": "Compute",
        "xpaths": ["./vcpu"],
        "protectable": True,
    },
    {
        "key": "iothreads",
        "label": "IO Threads",
        "group": "Compute",
        "xpaths": ["./iothreads", "./iothreadids"],
        "protectable": True,
    },
    {
        "key": "cputune",
        "label": "CPU Tuning",
        "group": "Compute",
        "xpaths": ["./cputune"],
        "protectable": True,
    },
    {
        "key": "numatune",
        "label": "NUMA Tuning",
        "group": "Compute",
        "xpaths": ["./numatune"],
        "protectable": True,
    },
    {
        "key": "cpu",
        "label": "CPU Model",
        "group": "Compute",
        "xpaths": ["./cpu"],
        "protectable": True,
    },
    # --- Boot & System ---
    {
        "key": "boot_order",
        "label": "Boot / OS",
        "group": "Boot & System",
        "xpaths": ["./os"],
        "protectable": True,
    },
    {
        "key": "sysinfo",
        "label": "SMBIOS / sysinfo",
        "group": "Boot & System",
        "xpaths": ["./sysinfo"],
        "protectable": True,
    },
    {
        "key": "resource",
        "label": "Resource Partition",
        "group": "Boot & System",
        "xpaths": ["./resource"],
        "protectable": True,
    },
    {
        "key": "features",
        "label": "Features",
        "group": "Boot & System",
        "xpaths": ["./features"],
        "protectable": True,
    },
    {
        "key": "clock",
        "label": "Clock & Timers",
        "group": "Boot & System",
        "xpaths": ["./clock"],
        "protectable": True,
    },
    {
        "key": "lifecycle",
        "label": "Lifecycle (poweroff/reboot/crash)",
        "group": "Boot & System",
        "xpaths": ["./on_poweroff", "./on_reboot", "./on_crash"],
        "protectable": True,
    },
    {
        "key": "pm",
        "label": "Power Mgmt",
        "group": "Boot & System",
        "xpaths": ["./pm"],
        "protectable": True,
    },
    # --- Storage ---
    {
        "key": "disks",
        "label": "Disks",
        "group": "Storage",
        "xpaths": ['.//devices/disk[@device="disk"]'],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "isos",
        "label": "ISOs / CDROMs",
        "group": "Storage",
        "xpaths": ['.//devices/disk[@device="cdrom"]'],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "floppies",
        "label": "Floppies",
        "group": "Storage",
        "xpaths": ['.//devices/disk[@device="floppy"]'],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "disk_cache",
        "label": "Disk Cache",
        "group": "Storage",
        "xpaths": [".//devices/disk/driver"],
        "protectable": True,
        "multi": True,
        "readonly_display": True,
    },
    {
        "key": "qos_disk",
        "label": "Disk QoS",
        "group": "Storage",
        "xpaths": [".//devices/disk/iotune"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "filesystem",
        "label": "Filesystem",
        "group": "Storage",
        "xpaths": [".//devices/filesystem"],
        "protectable": True,
        "multi": True,
    },
    # --- Display ---
    {
        "key": "video",
        "label": "Video",
        "group": "Display",
        "xpaths": [".//devices/video"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "graphics",
        "label": "Graphics",
        "group": "Display",
        "xpaths": [".//devices/graphics"],
        "protectable": True,
        "multi": True,
    },
    # --- Network ---
    {
        "key": "network",
        "label": "Interfaces",
        "group": "Network",
        "xpaths": [".//devices/interface"],
        "protectable": True,
        "multi": True,
    },
    # --- Devices ---
    {
        "key": "controllers",
        "label": "Controllers",
        "group": "Devices",
        "xpaths": [".//devices/controller"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "input",
        "label": "Input",
        "group": "Devices",
        "xpaths": [".//devices/input"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "console",
        "label": "Console",
        "group": "Devices",
        "xpaths": [".//devices/console"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "sound",
        "label": "Sound",
        "group": "Devices",
        "xpaths": [".//devices/sound"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "channels",
        "label": "Channels",
        "group": "Devices",
        "xpaths": ['.//devices/channel[@type="spicevmc"]'],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "redirdev",
        "label": "USB Redirectors",
        "group": "Devices",
        "xpaths": [".//devices/redirdev"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "rng",
        "label": "RNG",
        "group": "Devices",
        "xpaths": [".//devices/rng"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "memballoon",
        "label": "Memory Balloon",
        "group": "Devices",
        "xpaths": [".//devices/memballoon"],
        "protectable": True,
        "multi": True,
    },
    # --- Passthrough ---
    {
        "key": "hostdev",
        "label": "Passthrough (GPU/PCI/USB)",
        "group": "Passthrough",
        "xpaths": [".//devices/hostdev"],
        "protectable": True,
        "multi": True,
    },
    # --- Security ---
    {
        "key": "seclabel",
        "label": "Security Label",
        "group": "Security",
        "xpaths": ["./seclabel"],
        "protectable": True,
        "multi": True,
    },
    # --- System ---
    {
        "key": "domain_type",
        "label": "Domain Type",
        "group": "System",
        "xpaths": [".//devices/emulator"],
        "protectable": True,
        "extra_attrs": [(".", "type")],
    },
    {
        "key": "qemu_guest_agent",
        "label": "Guest Agent",
        "group": "System",
        "xpaths": [
            './/devices/channel[@type="unix"]/target[@name="org.qemu.guest_agent.0"]/..'
        ],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "shared_folder",
        "label": "Shared Folder",
        "group": "System",
        "xpaths": ['.//devices/channel[@type="spiceport"]'],
        "protectable": True,
        "multi": True,
    },
    # --- Metadata (always engine-managed) ---
    {
        "key": "metadata",
        "label": "Metadata",
        "group": "System",
        "xpaths": ["./metadata"],
        "protectable": False,
    },
]


def _elem_to_str(elem: ET.Element) -> str:
    """Convert an XML element to an indented string."""
    return ET.tostring(elem, encoding="unicode").strip()


def _section_allowed_tags(sdef: dict) -> set[str] | None:
    """Return the set of tag names a snippet for this section may contain.

    Derived from the section's xpaths: the last path segment (with predicates
    stripped) is the expected tag. Trailing `/..` is followed up one level so
    qemu_guest_agent (xpath ends in `target[...]/..`) yields `channel`.
    Sections without explicit xpath tags (or with an `extra_attrs` directive
    that targets `<domain>` itself) accept any tag and return ``None``.
    """
    tags: set[str] = set()
    for xp in sdef["xpaths"]:
        segs = xp.split("/")
        while segs and segs[-1] == "..":
            segs.pop()
            if segs:
                segs.pop()
        if not segs:
            continue
        last = re.sub(r"\[[^\]]*\]", "", segs[-1]).strip()
        if last and last != ".":
            tags.add(last)
    return tags or None


def _libvirt_toplevel_insert_index(parent: ET.Element, new_tag: str) -> int:
    """Return the index at which to insert <new_tag> as a direct child of
    <domain> so that the canonical libvirt element order is preserved.

    Walks the existing children left-to-right and returns the index of the
    first child whose canonical position is greater than ``new_tag``'s. Falls
    back to appending at the end if ``new_tag`` is unknown or all existing
    children come before it. Required because appending top-level elements at
    the end of <domain> places them after </devices>, which libvirt rejects
    for elements like <memoryBacking>, <on_poweroff>, etc.
    """
    if new_tag not in LIBVIRT_DOMAIN_ORDER:
        return len(list(parent))
    target_idx = LIBVIRT_DOMAIN_ORDER.index(new_tag)
    for i, child in enumerate(parent):
        if child.tag in LIBVIRT_DOMAIN_ORDER:
            if LIBVIRT_DOMAIN_ORDER.index(child.tag) > target_idx:
                return i
    return len(list(parent))


def _normalize_toplevel_order(root: ET.Element) -> None:
    """Stable-sort the direct children of <domain> into canonical libvirt
    order.

    Older versions of the editor's merge logic appended top-level elements
    past </devices>, leaving an invalid document that libvirt rejects on
    start. The XML is already persisted in that broken shape on existing
    installations, so preventing future corruption is not enough — every save
    must also re-sort into canonical order so a no-op save heals the
    document. Tags not present in LIBVIRT_DOMAIN_ORDER keep their relative
    order and land after the last known tag.
    """
    children = list(root)
    if not children:
        return

    n = len(LIBVIRT_DOMAIN_ORDER)

    def sort_key(idx_child: tuple[int, ET.Element]) -> tuple[int, int, int]:
        idx, child = idx_child
        if child.tag in LIBVIRT_DOMAIN_ORDER:
            return (LIBVIRT_DOMAIN_ORDER.index(child.tag), 0, idx)
        return (n, 1, idx)

    sorted_pairs = sorted(enumerate(children), key=sort_key)
    sorted_children = [c for _, c in sorted_pairs]

    if sorted_children == children:
        return

    for c in children:
        root.remove(c)
    for c in sorted_children:
        root.append(c)


def split_xml_sections(xml_str: str, protected_sections: list[str]) -> list[dict]:
    """Split a domain XML string into labeled sections.

    Returns a list of dicts with keys: key, label, xml, protected, protectable.
    """
    try:
        root = _safe_fromstring(xml_str)
    except ET.ParseError as e:
        raise Error(
            "bad_request",
            f"Invalid XML: {e}",
            traceback.format_exc(),
        )

    protected_set = set(protected_sections)
    sections = []

    for sdef in SECTION_DEFS:
        snippets = []
        for xpath in sdef["xpaths"]:
            if sdef.get("multi"):
                elems = root.findall(xpath)
                for elem in elems:
                    snippets.append(_elem_to_str(elem))
            else:
                elem = root.find(xpath)
                if elem is not None:
                    snippets.append(_elem_to_str(elem))

        # For domain_type extra_attrs (the type attribute on <domain>)
        if sdef.get("extra_attrs"):
            for path, attr in sdef["extra_attrs"]:
                target = root if path == "." else root.find(path)
                if target is not None and attr in target.attrib:
                    snippets.insert(
                        0, f'<!-- domain {attr}="{target.attrib[attr]}" -->'
                    )

        xml_snippet = "\n".join(snippets) if snippets else ""
        sections.append(
            {
                "key": sdef["key"],
                "label": sdef["label"],
                "group": sdef.get("group", ""),
                "xml": xml_snippet,
                "protected": sdef["key"] in protected_set,
                "protectable": sdef["protectable"],
            }
        )

    return sections


def merge_xml_sections(base_xml_str: str, edited_sections: dict) -> str:
    """Merge edited XML snippets back into the base XML.

    edited_sections is a dict: {section_key: xml_snippet_string, ...}
    Only protectable sections can be edited. Non-protectable sections are ignored.

    Returns the merged full XML string.
    """
    # Type validation (Finding 5)
    if not isinstance(edited_sections, dict):
        raise Error(
            "bad_request",
            "sections must be a dict",
            traceback.format_exc(),
        )

    try:
        root = _safe_fromstring(base_xml_str)
    except ET.ParseError as e:
        raise Error(
            "bad_request",
            f"Invalid base XML: {e}",
            traceback.format_exc(),
        )

    protectable_keys = {s["key"] for s in SECTION_DEFS if s["protectable"]}

    for key, snippet_xml in edited_sections.items():
        if key not in protectable_keys:
            continue

        # Type and size validation (Findings 4 & 5)
        if not isinstance(snippet_xml, str):
            raise Error(
                "bad_request",
                f"Section '{key}' value must be a string",
                traceback.format_exc(),
            )
        if len(snippet_xml) > MAX_SNIPPET_SIZE:
            raise Error(
                "bad_request",
                f"Section '{key}' exceeds maximum size ({MAX_SNIPPET_SIZE} bytes)",
                traceback.format_exc(),
            )

        sdef = next((s for s in SECTION_DEFS if s["key"] == key), None)
        if not sdef:
            continue

        if not snippet_xml.strip():
            # Empty snippet — remove matching elements
            for xpath in sdef["xpaths"]:
                if sdef.get("multi"):
                    for elem in root.findall(xpath):
                        (
                            elem.getparent()
                            if hasattr(elem, "getparent")
                            else _remove_elem(root, elem)
                        )
                else:
                    elem = root.find(xpath)
                    if elem is not None:
                        _remove_elem(root, elem)
            continue

        # Wrap snippet in a temporary root for parsing
        try:
            wrapper_xml = f"<_wrapper>{snippet_xml}</_wrapper>"
            new_elems = list(_safe_fromstring(wrapper_xml))
        except ET.ParseError as e:
            raise Error(
                "bad_request",
                f"Invalid XML in section '{key}': {e}",
                traceback.format_exc(),
            )

        # Hard validation: reject snippets whose root tag does not belong to
        # this section (e.g. pasting <hostdev> into the redirdev section).
        # Surfaces a clear bad_request instead of silently relocating the
        # element to a different section's xpath on the next split.
        allowed_tags = _section_allowed_tags(sdef)
        if allowed_tags is not None:
            mismatched = sorted({e.tag for e in new_elems if e.tag not in allowed_tags})
            if mismatched:
                expected = sorted(allowed_tags)
                raise Error(
                    "bad_request",
                    f"Section '{sdef.get('label', key)}' only accepts "
                    f"{expected} elements; got {mismatched}. "
                    f"The pasted XML belongs in a different section.",
                    traceback.format_exc(),
                )

        # Remove ALL old elements matching ANY xpath in this section
        first_parent = None
        first_idx = None
        for xpath in sdef["xpaths"]:
            for old_elem in root.findall(xpath):
                parent = _find_parent(root, old_elem)
                if parent is not None:
                    if first_parent is None:
                        first_parent = parent
                        first_idx = list(parent).index(old_elem)
                    parent.remove(old_elem)

        # Determine insertion parent and position
        if first_parent is None and new_elems:
            # No existing elements — figure out parent from xpath
            xpath = sdef["xpaths"][0]
            parent_path = xpath.rsplit("/", 1)[0] if "/" in xpath else "."
            parent_path = parent_path.replace(".", "").lstrip("/")
            first_parent = root.find(parent_path) if parent_path else root
            if first_parent is None:
                first_parent = root
            # When inserting at the root <domain>, place the new element at the
            # canonical libvirt position rather than at the end (which would
            # land after </devices> and libvirt would reject the document).
            if first_parent is root:
                first_idx = _libvirt_toplevel_insert_index(
                    first_parent, new_elems[0].tag
                )
            else:
                first_idx = len(list(first_parent))

        # Insert new elements at the position of the first removed element
        if first_parent is not None:
            for i, new_elem in enumerate(new_elems):
                first_parent.insert(first_idx + i, new_elem)

    # Stable-sort top-level <domain> children into canonical libvirt order.
    # Heals XMLs already corrupted by an older editor on the next save and
    # guarantees the merged document passes libvirt's element-order checks.
    _normalize_toplevel_order(root)

    # Validate the final XML
    merged_xml = ET.tostring(root, encoding="unicode")
    try:
        _safe_fromstring(merged_xml)
    except ET.ParseError as e:
        raise Error(
            "bad_request",
            f"Merged XML is invalid: {e}",
            traceback.format_exc(),
        )

    return merged_xml


def _remove_elem(root: ET.Element, elem: ET.Element) -> None:
    """Remove an element from anywhere in the tree."""
    parent = _find_parent(root, elem)
    if parent is not None:
        parent.remove(elem)


def _find_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    """Find the parent of a target element in the tree."""
    for parent in root.iter():
        if target in list(parent):
            return parent
    return None


def save_domain_xml_and_protected(
    domain_id: str, xml: str, protected_sections: list[str]
) -> None:
    """Save the merged XML and xml_protected_sections to the domain."""
    XmlSectionsProcessed.update_domain_xml_and_protected(
        domain_id, xml, protected_sections
    )


def get_domain_capabilities() -> dict:
    """Get cached domain capabilities from first online hypervisor."""
    return XmlSectionsProcessed.get_domain_capabilities()


def get_virt_install_xml_sections(virt_id: str) -> dict:
    """Return the split XML sections for a virt_install row.

    Mirrors v3 ``api_v3_admin_virt_install_xml_sections`` GET branch
    (``AdminDomainsView.py`` — commit 0d15e5511).
    """
    vi = XmlSectionsProcessed.get_virt_install(virt_id)
    if not vi:
        raise Error(
            "not_found",
            f"virt_install {virt_id} not found",
            traceback.format_exc(),
        )
    sections = split_xml_sections(vi.get("xml"), [])
    return {"sections": sections, "xml_full": vi.get("xml")}


def save_virt_install_xml_sections(virt_id: str, edited_sections: dict) -> dict:
    """Merge edited sections back into a virt_install row's XML.

    Mirrors v3 ``api_v3_admin_virt_install_xml_sections`` POST branch
    (``AdminDomainsView.py`` — commit 0d15e5511).
    """
    vi = XmlSectionsProcessed.get_virt_install(virt_id)
    if not vi:
        raise Error(
            "not_found",
            f"virt_install {virt_id} not found",
            traceback.format_exc(),
        )
    merged_xml = merge_xml_sections(vi.get("xml"), edited_sections)
    XmlSectionsProcessed.update_virt_install_xml(virt_id, merged_xml)
    return {"xml": merged_xml, "valid": True}


# ── save-as-virt_install (derive a virt_install from a live domain) ─────


_VIRT_INSTALL_DISK_PLACEHOLDERS = {
    "disk": "/home/tmp/disk.qcow2",
    "cdrom": "/home/tmp/cdrom.iso",
    "floppy": "/home/tmp/floppy.img",
}


def _generalize_xml(xml_str: str, name: str) -> str:
    """Generalize a domain XML for use as a virt_install template.

    Mirrors v3 ``api_xml_sections.generalize_xml``:
    - rename ``<name>`` to the new template name, generate a fresh
      ``<uuid>``,
    - replace domain-specific disk source paths with well-known
      placeholders based on ``device`` attribute,
    - drop runtime-only attributes (``backingStore``, disk ``index``),
    - reset graphics ports to ``-1``.
    """
    root = _safe_fromstring(xml_str)

    name_el = root.find("name")
    if name_el is not None:
        name_el.text = name
    uuid_el = root.find("uuid")
    if uuid_el is not None:
        uuid_el.text = str(uuid.uuid4())

    for disk in root.findall(".//devices/disk"):
        device = disk.get("device", "disk")
        placeholder = _VIRT_INSTALL_DISK_PLACEHOLDERS.get(device)
        if placeholder:
            src = disk.find("source")
            if src is not None:
                src.set("file", placeholder)
                if "index" in src.attrib:
                    del src.attrib["index"]
        for bs in disk.findall("backingStore"):
            disk.remove(bs)

    for gfx in root.findall(".//devices/graphics"):
        if "port" in gfx.attrib:
            gfx.set("port", "-1")

    return ET.tostring(root, encoding="unicode")


def _extract_virt_install_metadata(xml_str: str, name: str) -> dict:
    """Extract ``{www, icon, vers}`` fields for a virt_install row.

    Mirrors v3 ``api_xml_sections._extract_virt_install_metadata``.
    """
    root = _safe_fromstring(xml_str)

    www = ""
    for elem in root.iter():
        if "libosinfo" in (elem.tag or "") and "os" in (elem.tag or ""):
            www = elem.get("id", "")
            break

    name_lower = name.lower()
    if "windows" in name_lower or "win" in name_lower:
        icon = "windows"
    elif "redhat" in name_lower or "rhel" in name_lower or "centos" in name_lower:
        icon = "redhat"
    elif "fedora" in name_lower:
        icon = "fedora"
    elif "ubuntu" in name_lower:
        icon = "ubuntu"
    elif "debian" in name_lower:
        icon = "debian"
    elif "suse" in name_lower:
        icon = "suse"
    else:
        icon = "linux"

    vers = ""
    if www:
        parts = www.rstrip("/").split("/")
        if parts:
            vers = parts[-1]

    return {"www": www, "icon": icon, "vers": vers}


def save_as_virt_install(domain_id: str, edited_sections: dict, name: str) -> dict:
    """Merge domain XML sections and store as a new virt_install row.

    Mirrors v3 ``api_xml_sections.save_as_virt_install`` (commit
    0d15e5511): takes a live domain's xml, applies the edited
    sections, generalises placeholders, derives ``www``/``icon``/``vers``
    metadata and inserts a new ``virt_install`` row. The id is a
    slug of ``name``; duplicates raise 409.
    """
    if not name or not name.strip():
        raise Error(
            "bad_request",
            "Name cannot be empty",
            traceback.format_exc(),
        )
    name = name.strip()

    domain = XmlSectionsProcessed.get_domain(domain_id)
    if not domain:
        raise Error(
            "not_found",
            f"Domain {domain_id} not found",
            traceback.format_exc(),
        )
    merged_xml = merge_xml_sections(domain.get("xml"), edited_sections)
    generalized_xml = _generalize_xml(merged_xml, name)
    meta = _extract_virt_install_metadata(generalized_xml, name)

    virt_id = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")
    if not virt_id:
        raise Error(
            "bad_request",
            "Name must contain at least one alphanumeric character",
            traceback.format_exc(),
        )

    existing = XmlSectionsProcessed.get_virt_install(virt_id)
    if existing:
        raise Error(
            "conflict",
            f"A virt_install with ID '{virt_id}' already exists",
            traceback.format_exc(),
        )

    record = {
        "id": virt_id,
        "name": name,
        "vers": meta["vers"],
        "www": meta["www"],
        "icon": meta["icon"],
        "xml": generalized_xml,
    }
    XmlSectionsProcessed.insert_virt_install(record)
    return record
