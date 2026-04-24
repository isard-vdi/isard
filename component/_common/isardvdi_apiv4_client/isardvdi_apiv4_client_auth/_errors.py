"""Typed error wrapper for apiv4 responses.

openapi-python-client returns a ``Response`` for every call. On non-2xx
status codes, apiv4 conventionally sends a JSON body matching
``component/apiv4/src/api/schemas/common.ErrorResponse``
(``{"error", "description", "description_code", "debug"?}``).

``raise_for_status`` centralizes the "turn non-2xx into structured
exception" logic so every call site doesn't re-implement it.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol


class _ResponseLike(Protocol):
    status_code: Any
    content: bytes


@dataclass
class ApiV4Error(Exception):
    """Typed error for non-2xx apiv4 responses.

    ``errors.Is``-style matching isn't a Python thing; callers use
    ``except ApiV4Error as e: if e.status_code == 404: ...`` or match
    on ``e.description_code`` for business-logic branches (e.g. typed
    404 from ``RethinkBase.__init__``).
    """
    status_code: int
    error: str
    description: str = ""
    description_code: str = ""

    def __post_init__(self) -> None:
        super().__init__(self._format())

    @property
    def is_maintenance(self) -> bool:
        return self.status_code == 503 or self.error == "maintenance"

    def _format(self) -> str:
        parts = [f"apiv4 {self.status_code} {self.error}"]
        if self.description:
            parts.append(f"description={self.description!r}")
        if self.description_code:
            parts.append(f"description_code={self.description_code!r}")
        return " ".join(parts)

    def __str__(self) -> str:
        return self._format()


def raise_for_status(response: _ResponseLike) -> None:
    """Raise ``ApiV4Error`` if the response is non-2xx, otherwise pass."""
    status = int(response.status_code)
    if 200 <= status < 300:
        return

    try:
        body = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}

    if isinstance(body, dict):
        error = str(body.get("error") or "http_error")
        description = str(body.get("description") or response.content.decode("utf-8", "replace"))
        description_code = str(body.get("description_code") or "")
    else:
        error = "http_error"
        description = response.content.decode("utf-8", "replace")
        description_code = ""

    raise ApiV4Error(
        status_code=status,
        error=error,
        description=description,
        description_code=description_code,
    )
