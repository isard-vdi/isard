# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback
from xml.etree import ElementTree as ET
from xml.parsers.expat import ParserCreate

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

# Import the already-initialized db connection pool from api_admin
# (RDB can't be initialized after first request)
from .api_admin import db

# Maximum size for a single XML snippet (256 KB)
MAX_SNIPPET_SIZE = 256 * 1024


def _safe_fromstring(xml_str):
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
    # --- Compute ---
    {
        "key": "memory",
        "label": "Memory",
        "group": "Compute",
        "xpaths": ["./memory", "./currentMemory"],
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
    {
        "key": "audio",
        "label": "Audio",
        "group": "Devices",
        "xpaths": [".//devices/audio"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "serial",
        "label": "Serial",
        "group": "Devices",
        "xpaths": [".//devices/serial"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "watchdog",
        "label": "Watchdog",
        "group": "Devices",
        "xpaths": [".//devices/watchdog"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "panic",
        "label": "Panic Device",
        "group": "Devices",
        "xpaths": [".//devices/panic"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "shmem",
        "label": "Shared Memory",
        "group": "Devices",
        "xpaths": [".//devices/shmem"],
        "protectable": True,
        "multi": True,
    },
    {
        "key": "iommu",
        "label": "IOMMU",
        "group": "Devices",
        "xpaths": [".//devices/iommu"],
        "protectable": True,
    },
    # --- Security ---
    {
        "key": "tpm",
        "label": "TPM",
        "group": "Security",
        "xpaths": [".//devices/tpm"],
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
    # --- Catch-all for unmatched elements ---
    {
        "key": "other_toplevel",
        "label": "Other (top-level)",
        "group": "Other",
        "xpaths": [],
        "protectable": True,
        "multi": True,
        "catchall": "toplevel",
    },
    {
        "key": "other_devices",
        "label": "Other Devices",
        "group": "Other",
        "xpaths": [],
        "protectable": True,
        "multi": True,
        "catchall": "devices",
    },
]


def _elem_to_str(elem):
    """Convert an XML element to an indented string."""
    return ET.tostring(elem, encoding="unicode").strip()


def _find_section_elements(root, sdef):
    """Find all XML elements matching a section definition's xpaths."""
    elems = []
    for xpath in sdef["xpaths"]:
        if sdef.get("multi"):
            elems.extend(root.findall(xpath))
        else:
            elem = root.find(xpath)
            if elem is not None:
                elems.append(elem)
    return elems


def _collect_claimed_elements(root):
    """Collect all elements claimed by non-catchall SECTION_DEFS.

    Returns a set of element ids (id(elem)) that are matched by at least one
    normal section's xpaths.  Uses id() which is stable as long as the element
    objects remain alive in the same tree (guaranteed within a single call).
    """
    claimed = set()
    for sdef in SECTION_DEFS:
        if sdef.get("catchall"):
            continue
        for elem in _find_section_elements(root, sdef):
            claimed.add(id(elem))
    return claimed


def _get_unclaimed_children(root, claimed, catchall_type):
    """Return (parent, unclaimed_children) for a catch-all section type."""
    if catchall_type == "toplevel":
        parent = root
        devices_elem = root.find("./devices")
        unclaimed = [
            child
            for child in list(parent)
            if id(child) not in claimed and child is not devices_elem
        ]
    elif catchall_type == "devices":
        parent = root.find("./devices")
        if parent is None:
            return None, []
        unclaimed = [child for child in list(parent) if id(child) not in claimed]
    else:
        return None, []
    return parent, unclaimed


def _parse_snippet(snippet_xml, section_key):
    """Parse an XML snippet string into a list of elements."""
    try:
        wrapper_xml = f"<_wrapper>{snippet_xml}</_wrapper>"
        return list(_safe_fromstring(wrapper_xml))
    except ET.ParseError as e:
        raise Error(
            "bad_request",
            f"Invalid XML in section '{section_key}': {e}",
            traceback.format_exc(),
        )


def _build_parent_map(root):
    """Build a child->parent lookup dict in a single tree traversal."""
    return {id(child): parent for parent in root.iter() for child in parent}


def split_xml_sections(xml_str, protected_sections):
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
    claimed = _collect_claimed_elements(root)
    sections = []

    for sdef in SECTION_DEFS:
        snippets = []

        if sdef.get("catchall"):
            _, unclaimed = _get_unclaimed_children(root, claimed, sdef["catchall"])
            for child in unclaimed:
                snippets.append(_elem_to_str(child))
        else:
            for elem in _find_section_elements(root, sdef):
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


# Lookup dict for SECTION_DEFS by key (built once at import time)
_SDEF_BY_KEY = {s["key"]: s for s in SECTION_DEFS}


def merge_xml_sections(base_xml_str, edited_sections):
    """Merge edited XML snippets back into the base XML.

    edited_sections is a dict: {section_key: xml_snippet_string, ...}
    Only protectable sections can be edited. Non-protectable sections are ignored.

    Returns the merged full XML string.
    """
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

    # Process normal sections first, then catchall sections.
    # Compute claimed elements once after normal sections are done.
    catchall_edits = []

    for key, snippet_xml in edited_sections.items():
        if key not in protectable_keys:
            continue

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

        sdef = _SDEF_BY_KEY.get(key)
        if not sdef:
            continue

        if sdef.get("catchall"):
            catchall_edits.append((sdef, snippet_xml))
            continue

        if not snippet_xml.strip():
            parent_map = _build_parent_map(root)
            for elem in _find_section_elements(root, sdef):
                parent = parent_map.get(id(elem))
                if parent is not None:
                    parent.remove(elem)
            continue

        new_elems = _parse_snippet(snippet_xml, key)

        # Remove old elements, tracking insertion position
        parent_map = _build_parent_map(root)
        first_parent = None
        first_idx = None
        for old_elem in _find_section_elements(root, sdef):
            parent = parent_map.get(id(old_elem))
            if parent is not None:
                if first_parent is None:
                    first_parent = parent
                    first_idx = list(parent).index(old_elem)
                parent.remove(old_elem)

        # Determine insertion parent and position
        if first_parent is None and new_elems:
            xpath = sdef["xpaths"][0]
            parent_path = xpath.rsplit("/", 1)[0] if "/" in xpath else "."
            parent_path = parent_path.replace(".", "").lstrip("/")
            first_parent = root.find(parent_path) if parent_path else root
            if first_parent is None:
                first_parent = root
            first_idx = len(list(first_parent))

        if first_parent is not None:
            for i, new_elem in enumerate(new_elems):
                first_parent.insert(first_idx + i, new_elem)

    # Process catch-all sections with a single claimed-elements computation
    if catchall_edits:
        claimed = _collect_claimed_elements(root)
        for sdef, snippet_xml in catchall_edits:
            _merge_catchall_section(root, sdef, snippet_xml, claimed)

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


def _merge_catchall_section(root, sdef, snippet_xml, claimed):
    """Merge a catch-all section back into the XML tree."""
    parent, old_unclaimed = _get_unclaimed_children(root, claimed, sdef["catchall"])

    if parent is None and snippet_xml.strip():
        # "devices" catchall with no <devices> element yet
        parent = ET.SubElement(root, "devices")

    if parent is None:
        return

    for elem in old_unclaimed:
        parent.remove(elem)

    if not snippet_xml.strip():
        return

    for new_elem in _parse_snippet(snippet_xml, sdef["key"]):
        parent.append(new_elem)


def save_domain_xml_and_protected(domain_id, xml, protected_sections):
    """Save the merged XML and xml_protected_sections to the domain."""
    r.table("domains").get(domain_id).update(
        {
            "xml": xml,
            "create_dict": {"xml_protected_sections": r.literal(protected_sections)},
        }
    ).run(db.conn)


def get_domain_capabilities():
    """Get cached domain capabilities from first online hypervisor."""
    hyps = list(
        r.table("hypervisors")
        .has_fields({"info": {"domain_capabilities": True}})
        .filter(lambda hyp: hyp["info"]["domain_capabilities"].keys().count() > 0)
        .pluck({"info": {"domain_capabilities": True}})
        .limit(1)
        .run(db.conn)
    )
    if hyps:
        return hyps[0].get("info", {}).get("domain_capabilities", {})
    return {}
