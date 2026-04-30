#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI dependencies that normalise body parsing across content types.

The legacy admin frontend posts DataTables-style queries as
``application/x-www-form-urlencoded`` or ``multipart/form-data``;
modern callers (Vue 3, automation) post the same payload as JSON. The
admin log routes need to accept either. Per skill rule B7, that
content-type dispatch belongs in a dependency, not duplicated inline
across endpoints.
"""

import json as _json
from typing import Mapping

from api.services.error import Error
from fastapi import Request


async def parse_json_or_form(request: Request) -> Mapping:
    """Return the request body as a dict, regardless of content type.

    Accepts ``application/json``, ``application/x-www-form-urlencoded``
    and ``multipart/form-data``. Raises ``Error("bad_request", ...)``
    if neither parses cleanly.
    """
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        try:
            return await request.json()
        except _json.JSONDecodeError:
            raise Error("bad_request", "Request body must be valid JSON")
    try:
        return await request.form()
    except AssertionError:
        raise Error(
            "bad_request",
            "Request body must be JSON or form data",
        )
