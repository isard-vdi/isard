# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import re
import traceback
import uuid
from xml.etree import ElementTree as ET
from xml.parsers.expat import ParserCreate

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

# Import the already-initialized db connection pool from api_admin
# (RDB can't be initialized after first request)
from .api_admin import admin_table_get, db

# Maximum size for a single XML snippet (256 KB)
MAX_SNIPPET_SIZE = 256 * 1024

# Allowed libvirt <domain type="..."> values (see the domain_type section).
ALLOWED_DOMAIN_TYPES = {
    "kvm",
    "qemu",
    "xen",
    "lxc",
    "kqemu",
    "uml",
    "hvf",
    "vz",
    "bhyve",
}

# libvirt "foreign" namespaces that can appear in a domain document. Registering
# the conventional prefixes makes ElementTree round-trip them as e.g.
# <qemu:commandline> instead of <ns0:commandline>. The ns0 rewrite is harmful:
# the engine's add_qemu_pcie_reserve dedups the existing block with a regex that
# matches the literal "qemu:" prefix, so an "ns0:"-stored block is not removed
# and a duplicate <qemu:commandline> is appended on the next GPU start.
LIBVIRT_XML_NAMESPACES = {
    "qemu": "http://libvirt.org/schemas/domain/qemu/1.0",
    "lxc": "http://libvirt.org/schemas/domain/lxc/1.0",
}
for _ns_prefix, _ns_uri in LIBVIRT_XML_NAMESPACES.items():
    ET.register_namespace(_ns_prefix, _ns_uri)


def _safe_fromstring(xml_str):
    """Parse XML string with protection against entity expansion (Billion Laughs).

    Python's xml.etree.ElementTree uses expat which does NOT resolve external
    entities (SYSTEM/PUBLIC), but DOES expand internal entities without limit.
    We reject any XML containing a DOCTYPE declaration to prevent entity bombs.

    Comments are preserved (``insert_comments=True``) so a no-op save through the
    section editor does not silently strip ``<!-- ... -->`` from the stored
    domain XML.
    """
    stripped = xml_str.strip()
    if "<!DOCTYPE" in stripped or "<!ENTITY" in stripped:
        raise Error(
            "bad_request",
            "XML DOCTYPE and ENTITY declarations are not allowed",
            traceback.format_exc(),
        )
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.fromstring(stripped, parser=parser)


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
    {
        "key": "seclabel",
        "label": "Security Label",
        "group": "Security",
        "xpaths": ["./seclabel"],
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
            if id(child) not in claimed
            and child is not devices_elem
            and not callable(child.tag)
        ]
    elif catchall_type == "devices":
        parent = root.find("./devices")
        if parent is None:
            return None, []
        unclaimed = [
            child
            for child in list(parent)
            if id(child) not in claimed and not callable(child.tag)
        ]
    else:
        return None, []
    return parent, unclaimed


def _parse_snippet(snippet_xml, section_key):
    """Parse an XML snippet string into a list of elements.

    The wrapper declares libvirt's foreign namespaces (qemu/lxc) so a snippet
    that uses a prefix bound on the <domain> root in the real document — e.g. a
    natural ``<qemu:commandline>`` pasted into the "Other (top-level)" section —
    parses instead of failing with "unbound prefix". Comment nodes are dropped
    (they are not real elements for a section).
    """
    try:
        ns_decls = " ".join(
            f'xmlns:{p}="{u}"' for p, u in LIBVIRT_XML_NAMESPACES.items()
        )
        wrapper_xml = f"<_wrapper {ns_decls}>{snippet_xml}</_wrapper>"
        return [e for e in _safe_fromstring(wrapper_xml) if not callable(e.tag)]
    except ET.ParseError as e:
        raise Error(
            "bad_request",
            f"Invalid XML in section '{section_key}': {e}",
            traceback.format_exc(),
        )


def _section_allowed_tags(sdef):
    """Return the set of tag names a snippet for this section may contain.

    Derived from the section's xpaths: the last path segment (with predicates
    stripped) is the expected tag. Trailing `/..` is followed up one level so
    qemu_guest_agent (xpath ends in `target[...]/..`) yields `channel`. Catch-all
    sections accept any tag and return None.
    """
    if sdef.get("catchall"):
        return None
    tags = set()
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


def _build_parent_map(root):
    """Build a child->parent lookup dict in a single tree traversal."""
    return {id(child): parent for parent in root.iter() for child in parent}


def _libvirt_toplevel_insert_index(parent, new_tag):
    """Return the index at which to insert <new_tag> as a direct child of <domain>
    so that the canonical libvirt element order is preserved.

    Walks the existing children left-to-right and returns the index of the first
    child whose canonical position is greater than `new_tag`'s. Falls back to
    appending at the end if `new_tag` is unknown or all existing children come
    before it. Required because appending top-level elements at the end of
    <domain> places them after </devices>, which libvirt rejects for elements
    like <memoryBacking>, <on_poweroff>, etc.
    """
    if new_tag not in LIBVIRT_DOMAIN_ORDER:
        return len(list(parent))
    target_idx = LIBVIRT_DOMAIN_ORDER.index(new_tag)
    for i, child in enumerate(parent):
        if child.tag in LIBVIRT_DOMAIN_ORDER:
            if LIBVIRT_DOMAIN_ORDER.index(child.tag) > target_idx:
                return i
    return len(list(parent))


def _normalize_toplevel_order(root):
    """Stable-sort the direct children of <domain> into canonical libvirt order.

    Older versions of the editor's merge logic appended top-level elements past
    </devices>, leaving an invalid document that libvirt rejects on start. The
    XML is already persisted in that broken shape on existing installations, so
    preventing future corruption is not enough — every save must also re-sort
    into canonical order so a no-op save heals the document. Tags not present
    in LIBVIRT_DOMAIN_ORDER keep their relative order and land after the last
    known tag.
    """
    children = list(root)
    if not children:
        return

    n = len(LIBVIRT_DOMAIN_ORDER)

    def sort_key(idx_child):
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

    if root.tag != "domain":
        raise Error(
            "bad_request",
            f"Uploaded XML must be a libvirt <domain> document; got <{root.tag}>",
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
                "derived": sdef["key"] in _DERIVED_KEYS,
            }
        )

    return sections


# Lookup dict for SECTION_DEFS by key (built once at import time)
_SDEF_BY_KEY = {s["key"]: s for s in SECTION_DEFS}


def _xpath_steps(xp):
    """Normalize an xpath into a list of element-name steps for structural
    ancestor/descendant comparison.

    Predicates (`[@x="y"]`) are stripped, the leading `./` or `.//` anchor is
    dropped, and a trailing `/..` is resolved by popping its preceding step.
    Tags only — attribute filters intentionally don't participate, so e.g.
    `disks` (`.//devices/disk[@device="disk"]`) and `isos`
    (`.//devices/disk[@device="cdrom"]`) compare as equal here and neither
    becomes a descendant of the other.
    """
    cleaned = re.sub(r"\[[^\]]*\]", "", xp)
    cleaned = re.sub(r"^\./?/?", "", cleaned).strip("/")
    if not cleaned:
        return []
    steps = []
    for p in cleaned.split("/"):
        if p == "..":
            if steps:
                steps.pop()
        elif p and p != ".":
            steps.append(p)
    return steps


def _compute_derived_keys():
    """Return the set of section keys whose xpath targets a strict descendant
    of another section's xpath target.

    These sections are *derived informational views* of the parent section's
    XML — for example, `disk_cache` (`.//devices/disk/driver`) sits inside the
    `<disk>` elements owned by `disks` / `isos` / `floppies`. The parent is the
    single source of truth on save; the derived view's textarea contents are
    ignored by `merge_xml_sections` (and rendered read-only in the UI).
    """
    derived = set()
    for sdef in SECTION_DEFS:
        if sdef.get("catchall"):
            continue
        own = [_xpath_steps(xp) for xp in sdef["xpaths"]]
        for other in SECTION_DEFS:
            if other is sdef or other.get("catchall"):
                continue
            others = [_xpath_steps(xp) for xp in other["xpaths"]]
            for child_steps in own:
                if not child_steps:
                    continue
                for parent_steps in others:
                    if (
                        parent_steps
                        and len(child_steps) > len(parent_steps)
                        and child_steps[: len(parent_steps)] == parent_steps
                    ):
                        derived.add(sdef["key"])
                        break
                if sdef["key"] in derived:
                    break
            if sdef["key"] in derived:
                break
    return derived


_DERIVED_KEYS = _compute_derived_keys()


def _apply_extra_attrs(root, sdef, snippet_xml):
    """Apply (and strip) the ``extra_attrs`` a section encodes as a leading
    ``<!-- tag attr="value" -->`` comment.

    The split side stores root/element attributes that have no element of their
    own — currently only ``<domain type="...">`` for the domain_type section —
    as an HTML comment so they show in the textarea. ElementTree drops that
    comment when the snippet is parsed, so the value would be lost on merge. We
    read it from the raw snippet string, validate it, apply it to the target,
    and remove the comment so the remaining elements parse and validate cleanly.
    """
    for path, attr in sdef.get("extra_attrs", []):
        pattern = rf'<!--\s*\w+\s+{re.escape(attr)}="([^"]*)"\s*-->'
        match = re.search(pattern, snippet_xml)
        if match:
            target = root if path == "." else root.find(path)
            value = match.group(1)
            if attr == "type" and value not in ALLOWED_DOMAIN_TYPES:
                raise Error(
                    "bad_request",
                    f"Invalid domain type '{value}'; allowed: "
                    f"{sorted(ALLOWED_DOMAIN_TYPES)}",
                    traceback.format_exc(),
                )
            if target is not None:
                target.set(attr, value)
        snippet_xml = re.sub(pattern, "", snippet_xml)
    return snippet_xml


def merge_xml_sections(base_xml_str, edited_sections):
    """Merge edited XML snippets back into the base XML.

    edited_sections is a dict: {section_key: xml_snippet_string, ...}
    Only protectable sections can be edited. Non-protectable sections are ignored.

    Sections in `_DERIVED_KEYS` (xpaths that target descendants of another
    section's xpath, e.g. `disk_cache` and `qos_disk` inside `<disk>`) are
    informational views of the parent section. Their snippets here are ignored
    so a stale view does not silently overwrite an edit made via the parent
    section's snippet.

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

        if key in _DERIVED_KEYS:
            continue

        if sdef.get("catchall"):
            catchall_edits.append((sdef, snippet_xml))
            continue

        if sdef.get("extra_attrs"):
            snippet_xml = _apply_extra_attrs(root, sdef, snippet_xml)

        if not snippet_xml.strip():
            parent_map = _build_parent_map(root)
            for elem in _find_section_elements(root, sdef):
                parent = parent_map.get(id(elem))
                if parent is not None:
                    parent.remove(elem)
            continue

        new_elems = _parse_snippet(snippet_xml, key)

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

        # Determine insertion parent and position. Derive the structural parent
        # from the xpath via _xpath_steps (which correctly strips predicates and
        # resolves a trailing `/..`). The old string-munging approach mangled
        # predicate dots and ignored `/..`, so adding an absent qemu_guest_agent
        # channel landed it as a direct child of <domain> (invalid for libvirt).
        if first_parent is None and new_elems:
            xpath = sdef["xpaths"][0]
            parent_steps = _xpath_steps(xpath)[:-1]
            if parent_steps:
                first_parent = root.find("./" + "/".join(parent_steps))
                if first_parent is None and parent_steps == ["devices"]:
                    # device section but <devices> is absent: create it at the
                    # canonical top-level position.
                    idx = _libvirt_toplevel_insert_index(root, "devices")
                    first_parent = ET.Element("devices")
                    root.insert(idx, first_parent)
                if first_parent is None:
                    first_parent = root
            else:
                first_parent = root
            if first_parent is root:
                first_idx = _libvirt_toplevel_insert_index(
                    first_parent, new_elems[0].tag
                )
            else:
                first_idx = len(list(first_parent))

        if first_parent is not None:
            for i, new_elem in enumerate(new_elems):
                first_parent.insert(first_idx + i, new_elem)

    # Process catch-all sections with a single claimed-elements computation
    if catchall_edits:
        claimed = _collect_claimed_elements(root)
        for sdef, snippet_xml in catchall_edits:
            _merge_catchall_section(root, sdef, snippet_xml, claimed)

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


def _merge_catchall_section(root, sdef, snippet_xml, claimed):
    """Merge a catch-all section back into the XML tree.

    Preserves the original position of unclaimed elements: new elements are
    inserted at the index where the first old unclaimed element lived, instead
    of appending to the end of the parent. Without this, libvirt top-level
    elements like <memoryBacking>, <on_poweroff>, <seclabel> would be moved
    from their canonical position to after </devices>, which libvirt rejects.
    """
    parent, old_unclaimed = _get_unclaimed_children(root, claimed, sdef["catchall"])

    if parent is None and snippet_xml.strip():
        # "devices" catchall with no <devices> element yet
        parent = ET.SubElement(root, "devices")

    if parent is None:
        return

    insert_idx = None
    if old_unclaimed:
        insert_idx = list(parent).index(old_unclaimed[0])

    for elem in old_unclaimed:
        parent.remove(elem)

    if not snippet_xml.strip():
        return

    new_elems = _parse_snippet(snippet_xml, sdef["key"])
    if insert_idx is not None:
        for i, new_elem in enumerate(new_elems):
            parent.insert(insert_idx + i, new_elem)
    else:
        for new_elem in new_elems:
            parent.append(new_elem)


def save_domain_xml_and_protected(domain_id, xml, protected_sections):
    """Save the merged XML and xml_protected_sections to the domain."""
    r.table("domains").get(domain_id).update(
        {
            "xml": xml,
            "create_dict": {"xml_protected_sections": r.literal(protected_sections)},
        }
    ).run(db.conn)


def generalize_xml(xml_str, name):
    """Transform a domain XML into a generalized virt_install template.

    Replaces domain-specific values (disk paths, UUIDs, runtime artifacts)
    with generic placeholders matching the pattern in initdb/default_xmls/.
    """
    root = _safe_fromstring(xml_str)

    # Name and UUID
    name_el = root.find("name")
    if name_el is not None:
        name_el.text = name
    uuid_el = root.find("uuid")
    if uuid_el is not None:
        uuid_el.text = str(uuid.uuid4())

    # Disk source paths → placeholders
    _DISK_PLACEHOLDERS = {
        "disk": "/home/tmp/disk.qcow2",
        "cdrom": "/home/tmp/cdrom.iso",
        "floppy": "/home/tmp/floppy.img",
    }
    for disk in root.findall(".//devices/disk"):
        device = disk.get("device", "disk")
        placeholder = _DISK_PLACEHOLDERS.get(device)
        if placeholder:
            src = disk.find("source")
            if src is not None:
                src.set("file", placeholder)
                # Remove runtime attributes like index
                for attr in ["index"]:
                    if attr in src.attrib:
                        del src.attrib[attr]
        # Remove backingStore (runtime)
        for bs in disk.findall("backingStore"):
            disk.remove(bs)

    # Graphics: reset ports
    for gfx in root.findall(".//devices/graphics"):
        if "port" in gfx.attrib:
            gfx.set("port", "-1")
        if "tlsPort" in gfx.attrib:
            gfx.set("tlsPort", "-1")
        # Remove runtime listen attribute from <graphics> tag itself
        if "listen" in gfx.attrib:
            del gfx.attrib["listen"]
        if "websocket" in gfx.attrib:
            del gfx.attrib["websocket"]

    # Remove all <alias> elements (runtime artifacts)
    for alias in root.findall(".//{*}alias") + root.findall(".//alias"):
        parent = alias.getparent() if hasattr(alias, "getparent") else None
        if parent is None:
            # ElementTree doesn't have getparent, build parent map
            pass
    # Use parent map approach for ElementTree
    parent_map = {id(c): p for p in root.iter() for c in p}
    for alias in list(root.iter("alias")):
        parent = parent_map.get(id(alias))
        if parent is not None:
            parent.remove(alias)

    # Remove all <address> elements on devices (PCI/USB auto-assigned by libvirt)
    # Keep addresses on controllers as they define the topology
    _STRIP_ADDRESS_FROM = {
        "disk",
        "interface",
        "input",
        "sound",
        "video",
        "memballoon",
        "redirdev",
        "tpm",
        "rng",
        "watchdog",
    }
    for elem in root.iter():
        if elem.tag in _STRIP_ADDRESS_FROM:
            for addr in elem.findall("address"):
                elem.remove(addr)

    # Remove <nvram> (runtime-generated)
    os_el = root.find("os")
    if os_el is not None:
        for nvram in os_el.findall("nvram"):
            os_el.remove(nvram)

    # Strip specific machine version from <os><type machine=...>
    # e.g. "pc-q35-10.0" → "q35", "pc-i440fx-2.8" → "pc"
    os_type = root.find(".//os/type")
    if os_type is not None and os_type.get("machine"):
        machine = os_type.get("machine")
        if "q35" in machine:
            os_type.set("machine", "q35")
        elif "i440fx" in machine or machine.startswith("pc"):
            os_type.set("machine", "pc")

    # Remove runtime source paths on channels (e.g. unix socket paths)
    for channel in root.findall(".//devices/channel"):
        if channel.get("type") == "unix":
            for src in channel.findall("source"):
                channel.remove(src)
        # Remove target state attribute
        tgt = channel.find("target")
        if tgt is not None and "state" in tgt.attrib:
            del tgt.attrib["state"]

    # Remove Isard-specific metadata, keep libosinfo
    metadata = root.find("metadata")
    if metadata is not None:
        for child in list(metadata):
            # Keep comments and libosinfo namespace elements
            if callable(child.tag):
                continue
            if "libosinfo" not in (child.tag or ""):
                metadata.remove(child)

    # Remove console source (runtime)
    for console in root.findall(".//devices/console"):
        if "tty" in console.attrib:
            del console.attrib["tty"]
        for src in console.findall("source"):
            console.remove(src)

    # Remove serial source (runtime)
    for serial in root.findall(".//devices/serial"):
        for src in serial.findall("source"):
            serial.remove(src)

    return ET.tostring(root, encoding="unicode")


def _extract_virt_install_metadata(xml_str, name):
    """Extract metadata fields for a virt_install record from XML."""
    root = _safe_fromstring(xml_str)

    # Extract www from libosinfo
    www = ""
    for elem in root.iter():
        if "libosinfo" in (elem.tag or "") and "os" in (elem.tag or ""):
            www = elem.get("id", "")
            break

    # Derive icon from name
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

    # Derive version from www URL if possible
    vers = ""
    if www:
        # Pattern like http://microsoft.com/win/10 → "10"
        parts = www.rstrip("/").split("/")
        if parts:
            vers = parts[-1]

    return {"www": www, "icon": icon, "vers": vers}


def save_as_virt_install(domain_id, edited_sections, name):
    """Merge XML sections, generalize, and save as a new virt_install entry."""
    domain = admin_table_get("domains", domain_id, pluck=["xml"])
    merged_xml = merge_xml_sections(domain["xml"], edited_sections)
    generalized_xml = generalize_xml(merged_xml, name)
    meta = _extract_virt_install_metadata(generalized_xml, name)

    # Generate ID: slugify name
    virt_id = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_")
    if not virt_id:
        raise Error(
            "bad_request", "Name must contain at least one alphanumeric character"
        )

    # Check for duplicates
    existing = r.table("virt_install").get(virt_id).run(db.conn)
    if existing:
        raise Error(
            "conflict",
            f"A virt_install with ID '{virt_id}' already exists",
        )

    record = {
        "id": virt_id,
        "name": name,
        "vers": meta["vers"],
        "www": meta["www"],
        "icon": meta["icon"],
        "xml": generalized_xml,
    }
    r.table("virt_install").insert(record).run(db.conn)
    return record


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
