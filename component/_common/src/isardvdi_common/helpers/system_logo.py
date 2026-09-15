#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Naomi Hidalgo Piñar
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

"""Deployment-wide default logo/logo-collapsed, admin-editable.

Writes to the same admin-mounted static directory that
``api.routes.open`` already reads as its deployment-wide fallback
(``_STATIC_CUSTOM_LOGO_GLOB`` / ``_STATIC_CUSTOM_LOGO_COLLAPSED_GLOB``),
so no new fallback step or DB field is needed: a file present here is
"enabled", its absence is "disabled".
"""

import glob
import os

from isardvdi_common.helpers.category import _decode_data_url, _detect_mimetype

LOGO_BASE_PATH = "/static/custom"

_EXTENSIONS = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/webp": "webp",
}


def _glob_pattern(variant):
    return os.path.join(LOGO_BASE_PATH, f"{variant}.*")


def logo_status(variant="logo"):
    """Whether a system-wide logo file is currently present for this variant."""
    return bool(glob.glob(_glob_pattern(variant)))


def save_logo(data_url, variant="logo"):
    """Decode, validate and store a system-wide logo, replacing any previous one."""
    file_bytes = _decode_data_url(data_url)
    delete_logo(variant)
    ext = _EXTENSIONS[_detect_mimetype(file_bytes)]
    with open(os.path.join(LOGO_BASE_PATH, f"{variant}.{ext}"), "wb") as f:
        f.write(file_bytes)


def delete_logo(variant="logo"):
    """Remove any existing system-wide logo file for this variant."""
    for path in glob.glob(_glob_pattern(variant)):
        os.remove(path)
