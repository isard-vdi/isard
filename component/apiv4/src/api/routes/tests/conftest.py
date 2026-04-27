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
from typing import Literal
from unittest.mock import MagicMock

import httpx
import pytest
from api import app
from api.routes.tests.helpers import MockJWT, create_indexes
from cachetools import Cache
from fastapi.testclient import TestClient
from rethinkdb_mock import MockThink


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
