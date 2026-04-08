#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Simó Albert i Beltran
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

import base64
import os
import re

from isardvdi_common.provider_config import (
    provider_config_api_to_db,
    provider_config_db_to_api,
)
from rethinkdb import r

from .rethink_custom_base_factory import RethinkCustomBase

LOGO_BASE_PATH = "/opt/isard/frontend/custom/categories"
ALLOWED_LOGO_MIME_TYPES = {"image/svg+xml", "image/png", "image/webp"}
MAX_LOGO_SIZE = 512 * 1024  # 512KB

_SVG_DANGEROUS_TAGS = {
    "script",
    "handler",
    "foreignobject",
    "iframe",
    "embed",
    "object",
}
_SVG_EVENT_ATTR_RE = re.compile(r"\s+on\w+\s*=", re.IGNORECASE)
_SVG_JS_HREF_RE = re.compile(
    r'(?:href|xlink:href)\s*=\s*["\']?\s*javascript:', re.IGNORECASE
)


class Category(RethinkCustomBase):
    """
    Manage Category Objects

    Use constructor with keyword arguments to create new Category Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Category Object.
    """

    _rdb_table = "categories"

    def __getattr__(self, name):
        """
        Get an attribute from the Category object.

        When getting the 'authentication' attribute, converts provider config
        fields from DB format (comma-separated strings) to API format (lists).

        When getting the 'branding' attribute, injects logo.data as a base64
        data URL read from the filesystem if the logo is enabled and a file
        exists on disk.

        :param name: The attribute name to get.
        :type name: str
        :return: The attribute value.
        :rtype: any
        """
        value = super().__getattr__(name)
        if name == "authentication" and value:
            for provider_data in value.values():
                if isinstance(provider_data, dict):
                    for v in provider_data.values():
                        if isinstance(v, dict):
                            provider_config_db_to_api(v)
        if name == "branding" and value:
            logo = value.get("logo", {})
            logo.pop("data", None)
            try:
                logo_path = self._logo_path()
            except ValueError:
                logo_path = None
            if logo_path and logo.get("enabled") and os.path.isfile(logo_path):
                with open(logo_path, "rb") as f:
                    file_bytes = f.read()
                mimetype = _detect_mimetype(file_bytes)
                logo["data"] = (
                    f"data:{mimetype};base64,"
                    f"{base64.b64encode(file_bytes).decode()}"
                )
            value["logo"] = logo
        return value

    def __setattr__(self, name, value):
        """
        Set an attribute on the Category object.

        When setting the 'authentication' attribute, converts provider config
        fields from API format (lists) to DB format (comma-separated strings).

        When setting the 'branding' attribute:
        - Validates that the domain is not already in use by another category.
        - If logo.data contains a base64 data URL, decodes it and saves the
          file to disk, then strips logo.data before storing in DB.
        - If logo is disabled, deletes any existing logo file.

        :param name: The attribute name to set.
        :type name: str
        :param value: The value to set.
        :type value: any
        :raises ValueError: If the branding domain is already in use by another
            category or if the logo data is invalid.
        """
        if name == "authentication" and value:
            for provider_data in value.values():
                if isinstance(provider_data, dict):
                    for v in provider_data.values():
                        if isinstance(v, dict):
                            provider_config_api_to_db(v)
        if name == "branding" and value:
            enabled = value.get("domain", {}).get("enabled")
            domain_name = value.get("domain", {}).get("name")
            if enabled and domain_name:
                with self._rdb_context():
                    existing = list(
                        r.table("categories")
                        .filter(
                            lambda cat: (
                                cat["branding"]["domain"]["name"] == domain_name
                            )
                            & (cat["branding"]["domain"]["enabled"] == True)
                            & (cat["id"] != self.id)
                        )
                        .run(self._rdb_connection)
                    )
                if existing:
                    raise ValueError(f"Branding domain {domain_name} is already in use")

            logo = value.get("logo", {})
            logo_data = logo.get("data")

            if logo.get("enabled"):
                if logo_data:
                    file_bytes = _decode_data_url(logo_data)
                    self._save_logo(file_bytes)
            elif not logo.get("enabled", True):
                self._delete_logo()

            # Remove file data before storing in DB
            logo.pop("data", None)

        super().__setattr__(name, value)

    def _logo_path(self):
        """
        Get the validated logo file path for this category.

        :return: Absolute path to the logo file
        :rtype: str
        :raises ValueError: If the path would escape LOGO_BASE_PATH
        """
        logo_path = os.path.realpath(os.path.join(LOGO_BASE_PATH, self.id, "logo"))
        base = os.path.realpath(LOGO_BASE_PATH) + os.sep
        if not logo_path.startswith(base):
            raise ValueError("Invalid category ID for logo path")
        return logo_path

    def _save_logo(self, file_data):
        """
        Save a logo file for this category.

        :param file_data: The binary content of the logo file
        :type file_data: bytes
        """
        logo_path = self._logo_path()
        os.makedirs(os.path.dirname(logo_path), exist_ok=True)
        with open(logo_path, "wb") as f:
            f.write(file_data)

    def _delete_logo(self):
        """
        Delete the existing logo file for this category.
        """
        logo_path = self._logo_path()
        if os.path.isfile(logo_path):
            os.remove(logo_path)


def _sanitize_svg(svg_bytes):
    """
    Sanitize SVG content by removing dangerous tags and attributes.

    Strips <script>, <handler>, <foreignObject>, <iframe>, <embed>, <object>
    tags, on* event handler attributes, and javascript: hrefs.

    :param svg_bytes: Raw SVG file content
    :type svg_bytes: bytes
    :return: Sanitized SVG content
    :rtype: bytes
    """
    content = svg_bytes.decode("utf-8", errors="replace")

    for tag in _SVG_DANGEROUS_TAGS:
        content = re.sub(
            rf"<{tag}[\s>].*?</{tag}>",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        content = re.sub(
            rf"<{tag}\s*/>",
            "",
            content,
            flags=re.IGNORECASE,
        )

    content = _SVG_EVENT_ATTR_RE.sub(" data-removed=", content)
    content = _SVG_JS_HREF_RE.sub('href="', content)

    return content.encode("utf-8")


def _decode_data_url(data_url):
    """
    Decode a base64 data URL into bytes, validating the MIME type.

    :param data_url: Data URL string (e.g. "data:image/png;base64,iVBOR...")
    :type data_url: str
    :return: Decoded file bytes
    :rtype: bytes
    :raises ValueError: If the data URL format or MIME type is invalid
    """
    if not data_url.startswith("data:"):
        raise ValueError("Logo data must be a base64 data URL")

    try:
        header, b64_data = data_url.split(",", 1)
    except ValueError:
        raise ValueError("Invalid data URL format")

    # header is like "data:image/png;base64"
    mime_type = header.split(":")[1].split(";")[0]
    if mime_type not in ALLOWED_LOGO_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_LOGO_MIME_TYPES))
        raise ValueError(
            f"Logo MIME type '{mime_type}' not allowed. Allowed: {allowed}"
        )

    if (len(b64_data) * 3) // 4 > MAX_LOGO_SIZE:
        raise ValueError(
            f"Logo file too large ({(len(b64_data) * 3) // 4} bytes). Maximum: {MAX_LOGO_SIZE}"
        )

    try:
        file_bytes = base64.b64decode(b64_data)
    except Exception:
        raise ValueError("Invalid base64 data in logo")

    detected_mime = _detect_mimetype(file_bytes)
    if mime_type != detected_mime:
        raise ValueError(
            f"Declared MIME type '{mime_type}' does not match detected "
            f"type '{detected_mime}'"
        )

    if mime_type == "image/svg+xml":
        file_bytes = _sanitize_svg(file_bytes)

    return file_bytes


def _detect_mimetype(file_bytes):
    """
    Detect the MIME type of an image from its content.

    :param file_bytes: The file content (or at least the first 16 bytes)
    :type file_bytes: bytes
    :return: MIME type string
    :rtype: str
    """
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/svg+xml"
