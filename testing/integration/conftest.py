# SPDX-License-Identifier: AGPL-3.0-or-later

"""Session-wide fixtures for the integration suite.

The stack is expected to be Up before pytest runs — either via
``docker compose up -d`` locally, or via the ``integration:real`` CI
job that runs ``docker compose -f docker-compose.integration.yml up``
then execs this suite inside a sidecar container on the same network.

Environment variables:
    APIV4_URL, AUTH_URL, SOCKETIO_URL — stack endpoints (defaults point
        at the compose-network hostnames).
    E2E_ADMIN_USER / E2E_ADMIN_PWD — test admin account (default
        ``admin_e2e_01`` / ``IsardTest1!``; must be seeded by
        ``testing/db/populate_test_db.py``).
    E2E_NAMESPACE_PREFIX — override the per-session prefix (default is
        generated: ``e2e_real_<worker>_<unix_ts>_``).
    E2E_SKIP_STARTUP_CLEANUP — ``1`` to skip the pre-session cleanup.
    E2E_MEDIA_URL, E2E_REGISTRY_IMAGE — overrides for lifecycle tests.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterator

import pytest

from .helpers.cleanup import cleanup_by_prefix
from .helpers.client import IsardClient
from .helpers.sockets import SocketIOListener

log = logging.getLogger("integration.conftest")


def _worker_id(request: pytest.FixtureRequest) -> str:
    # pytest-xdist: "gw0", "gw1", ...; if not installed, falls back to "master".
    raw = os.environ.get("PYTEST_XDIST_WORKER", "master")
    return raw.replace("master", "w0")


@pytest.fixture(scope="session")
def admin_credentials() -> tuple[str, str, str]:
    return (
        os.environ.get("E2E_ADMIN_USER", "admin_e2e_01"),
        os.environ.get("E2E_ADMIN_PWD", "IsardTest1!"),
        os.environ.get("E2E_ADMIN_CATEGORY", "default"),
    )


@pytest.fixture(scope="session")
def admin_client(admin_credentials) -> Iterator[IsardClient]:
    user, pwd, cat = admin_credentials
    client = IsardClient()
    deadline = time.monotonic() + 60
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            client.login(user, pwd, category_id=cat)
            break
        except Exception as exc:  # pragma: no cover — we want the retry loop
            last_err = exc
            time.sleep(2)
    else:
        raise RuntimeError(f"admin login failed within 60s: {last_err}")
    yield client


@pytest.fixture(scope="session")
def test_namespace(request) -> str:
    override = os.environ.get("E2E_NAMESPACE_PREFIX")
    if override:
        return override
    worker = _worker_id(request)
    return f"e2e_real_{worker}_{int(time.time())}_"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after(
    admin_client: IsardClient, test_namespace: str
) -> Iterator[None]:
    # Startup: wipe leftovers from any prior crashed run (same host). This
    # is the only way re-running the suite after a crash is idempotent.
    if os.environ.get("E2E_SKIP_STARTUP_CLEANUP") != "1":
        try:
            cleanup_by_prefix(admin_client, "e2e_real_")
        except Exception as exc:
            log.warning("startup cleanup failed: %s", exc)

    yield

    # Teardown: only touch objects created by THIS session (the per-run
    # prefix). Never raise — a failed teardown must not mask a real test
    # failure.
    try:
        cleanup_by_prefix(admin_client, test_namespace)
    except Exception as exc:  # pragma: no cover
        log.warning("teardown cleanup failed: %s", exc)


@pytest.fixture
def ws(admin_client: IsardClient) -> Iterator[SocketIOListener]:
    listener = SocketIOListener(token=admin_client.token or "")
    listener.connect()
    try:
        yield listener
    finally:
        listener.disconnect()
