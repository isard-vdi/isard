# SPDX-License-Identifier: AGPL-3.0-or-later

"""Group failed responses into one bucket per traceback signature.

The apiv4 routes wrap exceptions as ``Error.create(..., traceback.format_exc())``.
The traceback ends up in the ``debug`` field of the JSON error response
when ``LOG_LEVEL=DEBUG``. Without DEBUG, only ``description`` is sent.

This module:
1. Pulls a signature from the response body when possible.
2. Falls back to a (status, description-prefix) tuple when the body
   lacks debug info.
3. Optionally enriches with the apiv4 container log entry that
   immediately followed the request (if the harness is run with
   docker logs access).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FRAME_RE = re.compile(
    r'File ".+?(?P<file>[^/"]+)", line (?P<line>\d+), in (?P<func>[\w_]+)'
)
_EXC_RE = re.compile(r"^(?P<cls>[\w.]+Error|[\w.]+Exception): (?P<msg>.*)", re.M)


@dataclass(frozen=True)
class ErrorSignature:
    exception_class: str
    exception_msg: str  # first line, possibly trimmed
    location: str  # "file.py:func" of the deepest frame
    status_code: int

    def short(self) -> str:
        loc = self.location or "?"
        msg = self.exception_msg or ""
        if len(msg) > 100:
            msg = msg[:97] + "..."
        return f"{self.exception_class} @ {loc}: {msg}"

    def bucket_key(self) -> str:
        # Group bucketing — drop the variable bits (object ids, paths
        # with uuids) so similar errors land together.
        msg_normalized = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            "<UUID>",
            self.exception_msg,
        )
        msg_normalized = re.sub(r"\s+", " ", msg_normalized).strip()
        if len(msg_normalized) > 80:
            msg_normalized = msg_normalized[:77] + "..."
        return f"{self.exception_class} @ {self.location}: {msg_normalized}"


def classify(status_code: int, body_text: str) -> ErrorSignature:
    """Best-effort traceback-signature extraction from a response body.

    Body is expected to be JSON with keys like ``error``, ``description``,
    ``debug``. ``debug`` carries the formatted traceback when LOG_LEVEL=DEBUG.
    """
    debug = ""
    description = ""
    try:
        body = json.loads(body_text) if body_text else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    if isinstance(body, dict):
        debug = str(body.get("debug") or "")
        description = str(body.get("description") or body.get("msg") or "")

    # FastAPI-style validation error
    if isinstance(body, dict) and body.get("detail") == "Method Not Allowed":
        return ErrorSignature(
            exception_class="MethodNotAllowed",
            exception_msg="Method Not Allowed",
            location="<router>",
            status_code=status_code,
        )

    if (
        isinstance(body, dict)
        and "details" in body
        and isinstance(body["details"], list)
    ):
        # Pydantic 422 → 400 wrapper
        first = body["details"][0] if body["details"] else {}
        loc = ".".join(str(x) for x in first.get("loc", []))
        msg = first.get("msg") or first.get("type") or "validation"
        return ErrorSignature(
            exception_class="ValidationError",
            exception_msg=f"{loc}: {msg}",
            location="<schema>",
            status_code=status_code,
        )

    exc_class = ""
    exc_msg = ""
    location = ""

    if debug:
        # Find deepest frame (last "File ..." line)
        frames = _FRAME_RE.findall(debug)
        if frames:
            file, line, func = frames[-1]
            location = f"{file}:{line}:{func}"
        exc_match = _EXC_RE.findall(debug)
        if exc_match:
            exc_class, exc_msg = exc_match[-1]

    if not exc_class:
        # Fall back to description
        exc_class = (
            "InternalServerError" if status_code >= 500 else f"HTTP{status_code}"
        )
        exc_msg = description or "(no debug info; LOG_LEVEL=DEBUG to capture)"

    return ErrorSignature(
        exception_class=exc_class,
        exception_msg=exc_msg.strip(),
        location=location or "<unknown>",
        status_code=status_code,
    )
