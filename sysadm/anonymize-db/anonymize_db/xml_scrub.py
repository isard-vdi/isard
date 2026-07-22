"""Strip secrets and host-specific paths from libvirt domain XML.

Conservative regex-based scrubber. We do not parse the XML to a DOM because
the upstream code stores it as a string and a round-trip through ElementTree
can subtly change formatting / attribute order in ways the engine then
re-parses; we only mask sensitive attributes and free-form text where present.
"""

from __future__ import annotations

import re

# <graphics ... passwd="..."> on spice/vnc devices
_GRAPHICS_PASSWD_RE = re.compile(r'(<graphics\b[^>]*?\s)passwd="[^"]*"')
# <channel><source path="/var/lib/.../socket"/></channel> — host paths
_CHANNEL_SRC_RE = re.compile(
    r'(<channel\b[^>]*>\s*<source\b[^>]*?\s)path="[^"]*"', re.DOTALL
)
# <serial><source><log file="..."/></source></serial>
_LOG_FILE_RE = re.compile(r'(<log\b[^>]*?\s)file="[^"]*"')
# <metadata> blocks may contain free-form notes — strip text content
_METADATA_NOTES_RE = re.compile(r"(<metadata>)(.*?)(</metadata>)", re.DOTALL)


def scrub_libvirt_xml(xml: str) -> str:
    xml = _GRAPHICS_PASSWD_RE.sub(r'\1passwd=""', xml)
    xml = _CHANNEL_SRC_RE.sub(r'\1path=""', xml)
    xml = _LOG_FILE_RE.sub(r'\1file=""', xml)
    # Drop any free-form notes inside <metadata>...</metadata>, keeping the
    # wrapper element so the XML stays well-formed.
    xml = _METADATA_NOTES_RE.sub(r"\1\3", xml)
    return xml
