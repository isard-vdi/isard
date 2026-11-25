# SPDX-License-Identifier: AGPL-3.0-or-later

"""Create media from a public URL that may refuse requests for a few minutes."""

import os
import time
from typing import Any, Callable

import pytest
import requests

REFUSED_CODE = "media_url_not_valid"

DEFAULT_MEDIA_URL = os.environ.get("E2E_MEDIA_URL") or (
    "https://gitlab.com/isard/isardvdi/-/raw/694ba43e8a77e04e13e373df63646071363b0f57/testing/media/isard-test.iso"
)


def _refused(resp: Any) -> bool:
    if isinstance(resp, dict):
        return resp.get("description_code") == REFUSED_CODE
    return int(resp.status_code) == 400 and REFUSED_CODE.encode() in resp.content


def upstream_status(url: str) -> str:
    """What the media source answers to this runner, as apiv4's probe asks it."""
    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            retry_after = resp.headers.get("Retry-After")
            suffix = f", Retry-After {retry_after}" if retry_after else ""
            return f"HTTP {resp.status_code}{suffix}"
    except requests.RequestException as exc:
        return f"{type(exc).__name__}: {exc}"


def create_media_from_url(
    send: Callable[[], Any], url: str, max_wait: float = 300
) -> Any:
    """Call ``send`` until apiv4 stops refusing ``url`` as unreachable, or fail."""
    deadline = time.monotonic() + max_wait
    delay = 10.0
    while True:
        resp = send()
        if not _refused(resp):
            return resp
        if time.monotonic() >= deadline:
            pytest.fail(
                f"apiv4 refused {url} as unreachable for {max_wait:.0f} s; "
                f"the source answers this runner {upstream_status(url)}"
            )
        time.sleep(delay)
        delay = min(delay * 2, 60.0)
