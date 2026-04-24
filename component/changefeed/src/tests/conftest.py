# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import sys
import types
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

_ASYNCAPI_DIR = (
    Path(__file__).resolve().parents[4] / "pkg" / "gen" / "asyncapi" / "changefeed"
)
if str(_ASYNCAPI_DIR) not in sys.path:
    sys.path.insert(0, str(_ASYNCAPI_DIR))

_COMMON_DIR = Path(__file__).resolve().parents[4] / "component" / "_common"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

if "rethinkdb" not in sys.modules:
    rethinkdb_stub = types.ModuleType("rethinkdb")
    rethinkdb_stub.r = object()  # type: ignore[attr-defined]
    sys.modules["rethinkdb"] = rethinkdb_stub

if "rethinkdb.errors" not in sys.modules:
    errors_stub = types.ModuleType("rethinkdb.errors")

    class _ReqlDriverError(Exception):
        pass

    errors_stub.ReqlDriverError = _ReqlDriverError  # type: ignore[attr-defined]
    sys.modules["rethinkdb.errors"] = errors_stub

if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")
    sys.modules["redis"] = redis_stub

if "redis.asyncio" not in sys.modules:
    redis_asyncio_stub = types.ModuleType("redis.asyncio")

    def _from_url(*args, **kwargs):  # noqa: ANN001, ANN002
        return None

    redis_asyncio_stub.from_url = _from_url  # type: ignore[attr-defined]
    sys.modules["redis.asyncio"] = redis_asyncio_stub

if "redis.exceptions" not in sys.modules:
    redis_exceptions_stub = types.ModuleType("redis.exceptions")

    class _ConnectionError(Exception):
        pass

    class _TimeoutError(Exception):
        pass

    redis_exceptions_stub.ConnectionError = _ConnectionError  # type: ignore[attr-defined]
    redis_exceptions_stub.TimeoutError = _TimeoutError  # type: ignore[attr-defined]
    sys.modules["redis.exceptions"] = redis_exceptions_stub

if "isardvdi_common.connections.rethink_connection_factory" not in sys.modules:
    factory_stub = types.ModuleType(
        "isardvdi_common.connections.rethink_connection_factory"
    )

    class _RethinkSharedConnection:
        def __init__(self, *args, **kwargs):
            pass

    factory_stub.RethinkSharedConnection = _RethinkSharedConnection  # type: ignore[attr-defined]
    sys.modules["isardvdi_common.connections.rethink_connection_factory"] = factory_stub
