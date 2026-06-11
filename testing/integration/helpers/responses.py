# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generic helpers for reading generated-client responses.

These are deliberately endpoint-agnostic: every test calls the generated
``*.sync_detailed`` operation directly (so a renamed route or retyped field
breaks at type-check time) and then narrows the typed ``Response`` here.

- ``expect`` asserts the status code and returns ``resp.parsed``.
- ``created_id`` is the ``SimpleResponse`` contract shared by every
  create / update / delete operation that echoes back an id.
"""

from __future__ import annotations

from typing import Any, TypeVar

from isardvdi_apiv4_client.models.simple_response import SimpleResponse
from isardvdi_apiv4_client.types import Response

T = TypeVar("T")


def expect(resp: Response[T], *ok: int) -> T:
    """Assert ``resp.status_code`` is one of ``ok`` (default ``200``) and
    return the parsed body.

    The return type is the operation's parsed union (e.g.
    ``ErrorResponse | list[AdminTemplateItem]``), so call sites keep the
    generated typing and narrow it with ``isinstance``. The response body
    is in the assertion message so a failing call points straight at the
    server error."""
    allowed = ok or (200,)
    assert (
        resp.status_code in allowed
    ), f"HTTP {resp.status_code} (wanted {allowed}): {resp.content[:300]!r}"
    assert resp.parsed is not None, f"empty body (HTTP {resp.status_code})"
    return resp.parsed


def created_id(resp: Response[Any]) -> str:
    """Return the id of a created / updated / deleted object.

    apiv4 answers those operations with ``SimpleResponse`` (a single
    ``id`` field), so narrowing here keeps every call site to one line."""
    parsed = expect(resp, 200, 201)
    assert isinstance(
        parsed, SimpleResponse
    ), f"expected SimpleResponse, got {type(parsed).__name__}: {resp.content[:300]!r}"
    return parsed.id
