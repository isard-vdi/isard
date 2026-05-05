#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import contextlib
import gc
import os
from typing import Literal
from unittest.mock import MagicMock

# Shared HS256 secret for JWTs minted by MockJWT and verified by
# isardvdi_common.helpers.token. setdefault so CI can still override.
os.environ.setdefault("API_ISARDVDI_SECRET", "test-secret")

import httpx
import pytest
from api.routes.tests.helpers import MockJWT, create_indexes
from api.services.error import Error
from cachetools import Cache
from fastapi.testclient import TestClient
from isardvdi_common.helpers.bastion import Bastion
from rethinkdb_mock import MockThink

from api import app


@pytest.fixture(autouse=True)
def _mock_bastion_grpc(monkeypatch):
    """Prevent tests from hitting the real haproxy-sync gRPC service.

    Two layers of isolation, matching the post-refactor architecture:

    1. ``configure_haproxy_bastion_client(provider)`` — the apiv4
       lifespan startup wires this in production. Tests don't run
       lifespan, so without an explicit registration here every call
       through ``Bastion.update_*`` or ``Targets.update`` would raise
       ``RuntimeError("haproxy-sync (haproxy_bastion) client not
       configured…")``. Register a MagicMock stub so the call sites
       resolve cleanly.

    2. ``Bastion._call_grpc_with_infinite_retry`` — the retry wrapper
       still gets monkeypatched because some call sites (notably
       ``sync_category_branding_domains``) inspect the response's
       ``failed_domains`` attribute, and the path needs a deterministic
       successful-sync shape. Without this the retry wrapper would
       call the MagicMock stub from #1 (returning another MagicMock)
       and the code path would behave semi-randomly.

    Tests that need to simulate sync failures override either layer:
    patch the provider for "stub failure" or patch
    ``Bastion.sync_category_branding_domains`` directly.
    """
    import isardvdi_common.connections.api_sessions as api_sessions
    import isardvdi_common.helpers.bastion as bastion_module

    # Layer 1: register a MagicMock provider. The provider is invoked
    # on every call site (it's not memoized), so returning a single
    # mock instance reuses the same MagicMock spec for all calls.
    haproxy_bastion_stub = MagicMock(name="HaproxyBastionStub")
    bastion_module.configure_haproxy_bastion_client(lambda: haproxy_bastion_stub)

    # Mirror for sessions client — apiv4 routes hit it via the
    # has_token dependency on every authenticated request. The
    # MockJWT path uses ``session_id="isardvdi-service"`` which
    # bypasses session validation, but other auth paths could still
    # call into the gRPC stub.
    sessions_stub = MagicMock(name="SessionsStub")
    api_sessions.configure_sessions_client(lambda: sessions_stub)

    # Layer 2: deterministic retry-wrapper response.
    success_response = MagicMock(name="DomainSyncResponse")
    success_response.failed_domains = []
    monkeypatch.setattr(
        Bastion,
        "_call_grpc_with_infinite_retry",
        staticmethod(MagicMock(return_value=success_response)),
    )

    yield

    # Reset providers between tests so leakage from one test's
    # custom registration doesn't affect another. The configure
    # functions take an arbitrary callable, so we restore "no
    # provider" by setting the private slot back to None.
    bastion_module._haproxy_bastion_client_provider = None
    api_sessions._sessions_client_provider = None


@pytest.fixture(autouse=True)
def _mock_log_user(monkeypatch):
    """Prevent ``log_user`` from opening a real TCP connection to
    ``isard-db:28015`` on every authenticated request.

    ``LogsUsers.__init__`` calls ``r.connect(host="isard-db", ...)`` —
    the actual rethinkdb driver, *not* the mock. When the host is
    unreachable (no container in the test env) the connect blocks for
    ~5 s before the swallow-and-warn try/except returns. Multiplied by
    ~1.8k authenticated tests this is hours per CI run, and it caused
    ``test_update_branding_does_not_block_on_grpc`` to fail at its 2 s
    ceiling for reasons unrelated to gRPC.

    apiv4 routes resolve to ``TokenFastAPI.log_user`` (an override that
    schedules ``LogsUsers`` via ``asyncio.to_thread``); patching only the
    base ``Token.log_user`` does not intercept the subclass, so the
    rethinkdb connect still fires from the worker thread. Patch the
    subclass directly.
    """
    noop = classmethod(lambda cls, payload: None)
    monkeypatch.setattr("isardvdi_common.helpers.token.Token.log_user", noop)
    monkeypatch.setattr("api.dependencies.jwt_token.TokenFastAPI.log_user", noop)


@pytest.fixture()
def client():
    """
    Fixture to create a TestClient for the FastAPI app.
    This client can be used in tests to make requests to the API.
    """
    return TestClient(app)


@pytest.fixture()
def test_client_with_conn(monkeypatch, client):

    def client_factory(
        *,
        db_tables_data,
        conn,
        url: str,
        method: Literal["GET", "POST", "PUT", "DELETE"] | str = "GET",
        body: dict = {},
        jwt: MockJWT = None,
    ):
        create_indexes(db_tables_data, conn)

        # Patch api_sessions
        monkeypatch.setattr("isardvdi_common.connections.api_sessions.get", MagicMock())

        # patch rethink_shared_connection with the mock connection
        monkeypatch.setattr(
            "isardvdi_common.connections.rethink_shared_connection.RethinkSharedConnection._rdb_context",
            contextlib.nullcontext,
        )
        monkeypatch.setattr(
            "isardvdi_common.connections.rethink_shared_connection.RethinkSharedConnection._rdb_connection",
            conn,
        )

        # Build the request
        if not url.startswith("/"):
            raise ValueError("URL must start with '/'")

        if not url.startswith("/api/v4"):
            url = f"/api/v4{url}"

        request_params = {
            "url": url,
        }
        if jwt:
            request_params["headers"] = jwt.header
        if body:
            request_params["json"] = body

        # Use ``client.request(method, url, ...)`` instead of e.g.
        # ``client.delete(url, json=...)`` because httpx's TestClient.delete
        # signature doesn't accept ``json=`` (it's an httpx convention that
        # body-on-DELETE goes via the generic request method). Matters for
        # routes like DELETE /admin/notification/{id} that accept a body.
        return client.request(method.upper(), **request_params)

    return client_factory


@pytest.fixture()
def test_client(monkeypatch, client, test_client_with_conn):

    def client_factory(
        url: str,
        method: Literal["GET", "POST", "PUT", "DELETE"] | str = "GET",
        body: dict = {},
        jwt: MockJWT = None,
        # ──────────────────────────────────────────────────────────────
        db_tables_data: dict[str, list[dict]] = {},
        remove_default_db: bool = False,
    ) -> httpx.Response:
        """
        Factory function to create a TestClient with a mock database connection.


        :param url: The URL to call.
        :param method: The HTTP method to use for the request.
        :param body: The JSON body to send with the request.
        :param jwt: A MockJWT instance to use for the request headers.

        ---

        :param db_tables_data: The database tables and their data.
        :param remove_default_db: If True, do not include default database data.
        """

        if not remove_default_db:
            # TODO: Save a more complete default db in a fixture
            default_tables = {
                "config": [
                    {
                        "id": 1,
                        "maintenance": False,
                    }
                ],
                "categories": [
                    {
                        "id": "default",
                    }
                ],
            }

            # Merge default tables with provided tables
            db_tables = {**default_tables, **db_tables_data}
        else:
            db_tables = db_tables_data
        mock_db = MockThink(
            {
                "dbs": {
                    "isard": {
                        "tables": db_tables,
                    }
                },
                "default": "isard",
            }
        )

        with mock_db.connect() as conn:
            return test_client_with_conn(
                db_tables_data=db_tables,
                conn=conn,
                url=url,
                method=method,
                body=body,
                jwt=jwt,
            )

    return client_factory


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "clear_cache: clear all cachetools caches before/after this test"
    )
    config.addinivalue_line(
        "markers", "setup_clear_cache: clear all cachetools caches before this test"
    )
    config.addinivalue_line(
        "markers", "teardown_clear_cache: clear all cachetools caches after this test"
    )


def pytest_runtest_setup(item):
    if "clear_cache" in item.keywords or "setup_clear_cache" in item.keywords:
        # clear caches before the test runs
        for obj in gc.get_objects():
            try:
                if isinstance(obj, Cache):
                    obj.clear()
            except Error:
                raise
            except Exception:
                pass


def pytest_runtest_teardown(item, nextitem):
    if "clear_cache" in item.keywords or "teardown_clear_cache" in item.keywords:
        # clear caches after the test runs
        for obj in gc.get_objects():
            try:
                if isinstance(obj, Cache):
                    obj.clear()
            except Error:
                raise
            except Exception:
                pass
