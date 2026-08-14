#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rejection of author-supplied HTML that can execute script when rendered.

Admin-authored rich text (notification bodies and footers) is rendered as HTML
by the clients, so the only thing standing between an author and script running
in every reader's session is what this module refuses to store.

Substring blacklists do not work here: ``"<script" not in body`` says nothing
about ``<img src=x onerror=alert(1)>`` or ``<svg onload=…>``, which need no
recognisable tag name at all. The checks below are shaped after the payload
instead — an event-handler attribute, a scripting URL scheme, or one of the tags
whose whole purpose is to pull in code.
"""

import re

# Tags that execute or embed regardless of their attributes. ``svg`` and ``math``
# are absent on purpose: they are legitimate content and their attack surface is
# the event-handler attribute, which _EVENT_ATTR_RE already covers.
_DANGEROUS_TAGS = (
    "script",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "applet",
    "base",
    "link",
    "meta",
    "form",
    "handler",
)

_DANGEROUS_TAG_RE = re.compile(
    r"<\s*/?\s*(?:%s)\b" % "|".join(_DANGEROUS_TAGS), re.IGNORECASE
)
# Any ``on*`` handler: onerror, onload, onmouseover, onfocus, … A space (or any
# whitespace) before the name is what distinguishes an attribute from a word.
_EVENT_ATTR_RE = re.compile(r"\son\w+\s*=", re.IGNORECASE)
# Scripting URL schemes, in any attribute. Browsers strip whitespace and control
# characters from inside a URL scheme before resolving it, so ``java\tscript:``
# runs; the separator is allowed between every character rather than only around
# the colon, and the colon itself may arrive HTML-encoded.
_SEP = r"[\s\x00-\x20]*"
_COLON = r"(?::|&#0*58;?|&#x0*3a;?)"


def _scheme(word):
    return _SEP.join(re.escape(char) for char in word)


_SCRIPT_URL_RE = re.compile(
    r"(?:{js}{sep}{colon}|{vbs}{sep}{colon}|{data}{sep}{colon}{sep}text{sep}/{sep}html)".format(
        js=_scheme("javascript"),
        vbs=_scheme("vbscript"),
        data=_scheme("data"),
        sep=_SEP,
        colon=_COLON,
    ),
    re.IGNORECASE,
)


def find_unsafe_html(value):
    """Return a short reason when ``value`` can execute script, else ``None``.

    The reason names the class of payload, never the payload itself, so it is
    safe to hand back to the caller in an error response.
    """
    if not value:
        return None
    text = str(value)
    if _DANGEROUS_TAG_RE.search(text):
        return "executable or embedding tag"
    if _EVENT_ATTR_RE.search(text):
        return "event handler attribute"
    if _SCRIPT_URL_RE.search(text):
        return "scripting url scheme"
    return None


def first_unsafe_html(*values):
    """``find_unsafe_html`` over several fields, returning the first reason."""
    for value in values:
        reason = find_unsafe_html(value)
        if reason:
            return reason
    return None
