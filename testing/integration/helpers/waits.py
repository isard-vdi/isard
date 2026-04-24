# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generic polling helpers. Prefer IsardClient.poll_* where possible; these
handle cases the domain-specific helpers don't cover."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 30.0,
    interval: float = 1.0,
    message: str = "predicate did not become truthy",
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise TimeoutError(f"{message} (waited {timeout}s)")


def poll_for(
    fn: Callable[[], T],
    *,
    accept: Callable[[T], bool],
    timeout: float = 30.0,
    interval: float = 1.0,
    message: str = "accept() never returned True",
) -> T:
    deadline = time.monotonic() + timeout
    last: T = None  # type: ignore[assignment]
    while time.monotonic() < deadline:
        last = fn()
        if accept(last):
            return last
        time.sleep(interval)
    raise TimeoutError(f"{message}; last value: {last!r} (waited {timeout}s)")
