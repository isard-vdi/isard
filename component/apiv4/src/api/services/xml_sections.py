# XML sections editor service
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
import traceback
import uuid
from xml.etree import ElementTree as ET
from xml.parsers.expat import ParserCreate

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import RethinkDB, r

# Import the already-initialized db connection pool from api_admin
# (RDB can't be initialized after first request)


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
]


def _elem_to_str(elem):
    """Convert an XML element to an indented string."""
    return ET.tostring(elem, encoding="unicode").strip()


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


def merge_xml_sections(base_xml_str, edited_sections):
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
            first_idx = len(list(first_parent))

        # Insert new elements at the position of the first removed element
        if first_parent is not None:
            for i, new_elem in enumerate(new_elems):
                first_parent.insert(first_idx + i, new_elem)

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


def _remove_elem(root, elem):
    """Remove an element from anywhere in the tree."""
    parent = _find_parent(root, elem)
    if parent is not None:
        parent.remove(elem)


def _find_parent(root, target):
    """Find the parent of a target element in the tree."""
    for parent in root.iter():
        if target in list(parent):
            return parent
    return None


def save_domain_xml_and_protected(domain_id, xml, protected_sections):
    """Save the merged XML and xml_protected_sections to the domain."""
    with RethinkSharedConnection._rdb_context():
        r.table("domains").get(domain_id).update(
            {
                "xml": xml,
                "create_dict": {
                    "xml_protected_sections": r.literal(protected_sections)
                },
            }
        ).run(RethinkSharedConnection._rdb_connection)


def get_domain_capabilities():
    """Get cached domain capabilities from first online hypervisor."""
    with RethinkSharedConnection._rdb_context():
        hyps = list(
            r.table("hypervisors")
            .has_fields({"info": {"domain_capabilities": True}})
            .filter(lambda hyp: hyp["info"]["domain_capabilities"].keys().count() > 0)
            .pluck({"info": {"domain_capabilities": True}})
            .limit(1)
            .run(RethinkSharedConnection._rdb_connection)
        )
    if hyps:
        return hyps[0].get("info", {}).get("domain_capabilities", {})
    return {}


def get_virt_install_xml_sections(virt_id):
    """Return the split XML sections for a virt_install row.

    Mirrors v3 ``api_v3_admin_virt_install_xml_sections`` GET branch
    (``AdminDomainsView.py`` — commit 0d15e5511).
    """
    with RethinkSharedConnection._rdb_context():
        vi = (
            r.table("virt_install")
            .get(virt_id)
            .default(None)
            .run(RethinkSharedConnection._rdb_connection)
        )
    if not vi:
        raise Error(
            "not_found",
            f"virt_install {virt_id} not found",
            traceback.format_exc(),
        )
    sections = split_xml_sections(vi.get("xml"), [])
    return {"sections": sections, "xml_full": vi.get("xml")}


def save_virt_install_xml_sections(virt_id, edited_sections):
    """Merge edited sections back into a virt_install row's XML.

    Mirrors v3 ``api_v3_admin_virt_install_xml_sections`` POST branch
    (``AdminDomainsView.py`` — commit 0d15e5511).
    """
    with RethinkSharedConnection._rdb_context():
        vi = (
            r.table("virt_install")
            .get(virt_id)
            .default(None)
            .run(RethinkSharedConnection._rdb_connection)
        )
    if not vi:
        raise Error(
            "not_found",
            f"virt_install {virt_id} not found",
            traceback.format_exc(),
        )
    merged_xml = merge_xml_sections(vi.get("xml"), edited_sections)
    with RethinkSharedConnection._rdb_context():
        r.table("virt_install").get(virt_id).update({"xml": merged_xml}).run(
            RethinkSharedConnection._rdb_connection
        )
    return {"xml": merged_xml, "valid": True}


# ── save-as-virt_install (derive a virt_install from a live domain) ─────


_VIRT_INSTALL_DISK_PLACEHOLDERS = {
    "disk": "/home/tmp/disk.qcow2",
    "cdrom": "/home/tmp/cdrom.iso",
    "floppy": "/home/tmp/floppy.img",
}


def _generalize_xml(xml_str, name):
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


def _extract_virt_install_metadata(xml_str, name):
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


def save_as_virt_install(domain_id, edited_sections, name):
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

    with RethinkSharedConnection._rdb_context():
        domain = (
            r.table("domains")
            .get(domain_id)
            .default(None)
            .run(RethinkSharedConnection._rdb_connection)
        )
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

    with RethinkSharedConnection._rdb_context():
        existing = (
            r.table("virt_install")
            .get(virt_id)
            .run(RethinkSharedConnection._rdb_connection)
        )
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
    with RethinkSharedConnection._rdb_context():
        r.table("virt_install").insert(record).run(
            RethinkSharedConnection._rdb_connection
        )
    return record
