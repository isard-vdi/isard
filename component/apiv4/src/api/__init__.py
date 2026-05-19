#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import asyncio
import concurrent.futures
import logging as log
import os
from contextlib import asynccontextmanager

from api.dependencies.jwt_token import (
    has_email_verification_required_or_login_token,
    has_migration_required_or_login_token,
    has_token,
    has_token_direct_viewer,
    has_token_disclaimer,
    has_token_maintenance,
    has_token_password_reset_login,
    has_token_register,
    is_admin,
    is_admin_or_manager,
    is_not_user,
)
from api.services.error import Error
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.cards import Cards
from isardvdi_common.helpers.maintenance import Maintenance
from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue
from pydantic import ValidationError

from .schemas.common import ErrorResponse


def _sync_haproxy_maps():
    """Sync bastion maps and category branding domains to HAProxy (blocking)."""
    Bastion.update_bastion_haproxy_map()
    Bastion.sync_category_branding_domains()


def _wire_grpc_providers():
    """Register concrete gRPC stubs as providers for the shared
    ``isardvdi_common`` modules.

    Called once at lifespan startup before any request runs. The
    shared modules (``api_sessions``, ``bastion``, ``targets``) used
    to build their own gRPC channels at module-load time, which (a)
    opened a TCP channel for every importer of ``isardvdi_common``
    regardless of whether they would call the functions and (b) ran
    a misconfigured ``grpc.experimental.gevent.init_gevent()`` that
    SIGSEGV'd apiv4's worker under load (incidents 2026-05-01 and
    2026-05-05). Both concerns are now apiv4's responsibility:
    ``api.connections.grpc_client`` owns the factories, and the
    closures here memoize one stub per uvicorn worker process.

    Extracted from ``lifespan`` so it can be unit-tested in
    isolation without standing up the full lifespan side-effect
    surface (Maintenance.initialization, pool warm-up, etc.).
    """
    from api.connections.grpc_client import (
        create_haproxy_bastion_client,
        create_sessions_client,
    )
    from isardvdi_common.connections import api_sessions as _api_sessions
    from isardvdi_common.helpers import bastion as _bastion

    _sessions_stub = create_sessions_client("isard-sessions", 1312)
    _haproxy_bastion_stub = create_haproxy_bastion_client("isard-portal", 1312)
    _api_sessions.configure_sessions_client(lambda: _sessions_stub)
    _bastion.configure_haproxy_bastion_client(lambda: _haproxy_bastion_stub)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    #
    # Wire up the gRPC client providers in ``isardvdi_common`` before any
    # business logic runs. See ``_wire_grpc_providers`` docstring above
    # for the full incident chain that motivated extracting this from
    # the lifespan body — short version: we register closures so the
    # shared modules fetch the same long-lived stub on every call,
    # one channel per uvicorn worker process.
    _wire_grpc_providers()

    Maintenance.initialization()
    Cards.seed_stock_cards()
    Cards.cleanup_missing()

    # Default-executor sizing must match RETHINKDB_POOL_SIZE: each
    # `await asyncio.to_thread(...)` parks a thread that then calls
    # `with cls._rdb_context()`. If the executor is wider than the
    # pool, threads 21..N block in `acquire(timeout=30s)` and trip
    # `PoolExhaustedError` → 503 (the documented +50-connection hang
    # in user memory `reference_apiv4_hang_pool_starvation`). The
    # invariant is `executor <= pool`; we default both to 128 and
    # warn if env overrides break it.
    pool_size = int(os.environ.get("RETHINKDB_POOL_SIZE", "128"))
    workers = int(os.environ.get("APIV4_EXECUTOR_MAX_WORKERS", str(pool_size)))
    if workers > pool_size:
        log.warning(
            "APIV4_EXECUTOR_MAX_WORKERS=%d > RETHINKDB_POOL_SIZE=%d — "
            "threads will block on pool.acquire under load and trip "
            "PoolExhaustedError. Lower the executor or raise the pool.",
            workers,
            pool_size,
        )
    asyncio.get_running_loop().set_default_executor(
        concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="apiv4-rdb"
        )
    )
    log.info(
        "apiv4 executor=%d pool=%d (sized for ~%d simultaneous rdb queries)",
        workers,
        pool_size,
        min(workers, pool_size),
    )

    # Eagerly open RETHINKDB_POOL_SIZE/2 connections so the first burst
    # of traffic doesn't race acquire(timeout=…) while the pool grows
    # on demand. Without this the cold-start window produces a flurry
    # of 503s when load hits before the pool has a chance to fill.
    # Best-effort: any failure is logged and the service still starts
    # (the pool will grow on demand later).
    try:
        from isardvdi_common.connections.rethink_shared_connection import warm_pool

        await asyncio.to_thread(warm_pool)
    except Exception:
        log.warning("Pool warm-up at lifespan startup failed (continuing)")

    # Background pool-headroom sampler. Polls _pool_stats_extra() every
    # POOL_SAMPLE_INTERVAL_S seconds and tracks the peak in_use seen.
    # At shutdown we emit a single summary line so a load-test pass
    # produces a one-shot "headroom = pool_max_size - peak_in_use"
    # number for tuning the executor/pool pair without tailing Loki.
    pool_peak_state = {"peak_in_use": 0, "samples": 0}
    pool_sampler_task = None
    try:
        from isardvdi_common.connections.rethink_shared_connection import (
            _pool_stats_extra,
        )

        sample_interval_s = float(os.environ.get("APIV4_POOL_SAMPLE_INTERVAL_S", "1.0"))

        async def _sample_pool_headroom():
            while True:
                stats = _pool_stats_extra()
                in_use = stats.get("pool_in_use", 0) or 0
                if in_use > pool_peak_state["peak_in_use"]:
                    pool_peak_state["peak_in_use"] = in_use
                pool_peak_state["samples"] += 1
                await asyncio.sleep(sample_interval_s)

        pool_sampler_task = asyncio.create_task(_sample_pool_headroom())
    except Exception:
        log.warning("Pool-headroom sampler failed to start (telemetry only, non-fatal)")

    try:
        _sync_haproxy_maps()
    except Exception:
        log.warning("Bastion haproxy map update failed (bastion may be disabled)")

    # Watch haproxy-sync health and resync on reconnection
    health_task = None
    try:
        from api.connections.grpc_client import (
            async_watch_health_check,
            create_haproxy_sync_client,
        )

        _, haproxy_channel = create_haproxy_sync_client("isard-portal", 1312)
        health_task = asyncio.create_task(
            async_watch_health_check(
                haproxy_channel,
                "haproxy_sync.v1.HaproxySyncService",
                _sync_haproxy_maps,
            )
        )
    except Exception:
        log.warning("Failed to start HAProxy health watch")

    recycle_bin_queue = RecycleBinDeleteQueue()
    await recycle_bin_queue.initialize()
    await recycle_bin_queue.start()

    yield

    # Shutdown
    if health_task:
        health_task.cancel()
    if pool_sampler_task:
        pool_sampler_task.cancel()
        try:
            await pool_sampler_task
        except (asyncio.CancelledError, Exception):
            pass
    headroom = pool_size - pool_peak_state["peak_in_use"]
    log.info(
        "apiv4 pool peak in_use=%d / max=%d (headroom=%d, samples=%d)",
        pool_peak_state["peak_in_use"],
        pool_size,
        headroom,
        pool_peak_state["samples"],
    )
    await recycle_bin_queue.stop()


_debug_mode = os.environ.get("USAGE", "production") != "production"

app = FastAPI(
    title="IsardVDI API",
    description="IsardVDI API v4",
    version="4.0.0-alpha1",
    openapi_url="/api/v4/openapi.json" if _debug_mode else None,
    docs_url="/api/v4/docs" if _debug_mode else None,
    redoc_url="/api/v4/redoc" if _debug_mode else None,
    lifespan=lifespan,
    swagger_ui_parameters={
        "docExpansion": "none",
        "filter": True,
        "tryItOutEnabled": True,
        "persistAuthorization": True,
        "deepLinking": True,
    },
)

cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _error_response_body(
    *,
    error: str,
    description: str = "",
    description_code: str | None = None,
    msg: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Build a body matching the ``ErrorResponse`` schema in
    ``schemas/common.py``.

    Every required field is populated (with empty strings or ``{}``
    where appropriate) so consumers using the strictly-typed generated
    ``isardvdi_apiv4_client.ErrorResponse.from_dict`` decoder parse the
    body without ``KeyError``. Internal debug fields are left blank to
    satisfy OWASP A05. Handler-specific structured data (e.g. pydantic
    ``exc.errors()``) is merged via ``extra`` and lands as additional
    properties on the response.
    """
    body = {
        "error": error,
        "msg": msg if msg is not None else error,
        "description_code": description_code or error,
        "function": "",
        "function_call": "",
        "description": description,
        "debug": "",
        "request": "",
        "data": "",
        "params": {},
    }
    if extra:
        body.update(extra)
    return body


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """
    Global handler for FastAPI RequestValidationError exceptions
    (automatic request body/query parameter validation failures).
    """
    return JSONResponse(
        status_code=400,
        content=_error_response_body(
            error="validation_error",
            description="Request validation failed",
            extra={"details": jsonable_encoder(exc.errors())},
        ),
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """
    Global handler for Pydantic ValidationError exceptions
    raised manually in service code.
    """
    return JSONResponse(
        status_code=400,
        content=_error_response_body(
            error="validation_error",
            description="Request validation failed",
            extra={"details": exc.errors()},
        ),
    )


open_router = APIRouter(
    tags=["open"],
    prefix="/api/v4",
)
token_router = APIRouter(
    tags=["role_user", "role_advanced", "role_manager", "role_admin"],
    prefix="/api/v4",
    dependencies=[Depends(has_token)],
    responses={401: {"model": ErrorResponse}},
)
advanced_router = APIRouter(
    tags=["role_advanced", "role_manager", "role_admin"],
    prefix="/api/v4",
    dependencies=[Depends(is_not_user)],
    responses={401: {"model": ErrorResponse}},
)
manager_router = APIRouter(
    tags=["role_manager", "role_admin"],
    prefix="/api/v4",
    dependencies=[Depends(is_admin_or_manager)],
    responses={401: {"model": ErrorResponse}},
)
admin_router = APIRouter(
    tags=["role_admin"],
    prefix="/api/v4",
    dependencies=[Depends(is_admin)],
    responses={401: {"model": ErrorResponse}},
)
maintenance_router = APIRouter(
    tags=["maintenance"],
    prefix="/api/v4",
    dependencies=[Depends(has_token_maintenance)],
    responses={401: {"model": ErrorResponse}},
)

register_router = APIRouter(
    tags=["register"],
    prefix="/api/v4",
    dependencies=[Depends(has_token_register)],
    responses={401: {"model": ErrorResponse}},
)

password_reset_router = APIRouter(
    tags=["password_reset"],
    prefix="/api/v4",
    dependencies=[Depends(has_token_password_reset_login)],
    responses={401: {"model": ErrorResponse}},
)

disclaimer_router = APIRouter(
    tags=["disclaimer"],
    prefix="/api/v4",
    dependencies=[Depends(has_token_disclaimer)],
    responses={401: {"model": ErrorResponse}},
)

direct_viewer_router = APIRouter(
    tags=["direct_viewer"],
    prefix="/api/v4",
    dependencies=[Depends(has_token_direct_viewer)],
    responses={401: {"model": ErrorResponse}},
)

migration_router = APIRouter(
    tags=["migration"],
    prefix="/api/v4",
    dependencies=[Depends(has_migration_required_or_login_token)],
    responses={401: {"model": ErrorResponse}},
)

email_verification_router = APIRouter(
    tags=["email_verification"],
    prefix="/api/v4",
    dependencies=[Depends(has_email_verification_required_or_login_token)],
    responses={401: {"model": ErrorResponse}},
)

from .routes import (
    bastion,
    cards,
    categories,
    deployments,
    groups,
    login,
    login_config,
    maintenance,
    media,
    migrations,
    notifications,
    open,
    quota,
    recycle_bin,
    storage,
    storage_pools,
    tasks,
    user_networks,
    users,
    vpn,
)
from .routes.admin import alloweds as admin_alloweds
from .routes.admin import analytics as admin_analytics
from .routes.admin import authentication as admin_authentication
from .routes.admin import backups as admin_backups
from .routes.admin import categories as admin_categories
from .routes.admin import domains as admin_domains
from .routes.admin import downloads as admin_downloads
from .routes.admin import hypervisors as admin_hypervisors
from .routes.admin import login_config as admin_login_config
from .routes.admin import media as admin_media
from .routes.admin import notifications as admin_notifications
from .routes.admin import notify as admin_notify
from .routes.admin import operations as admin_operations
from .routes.admin import queues as admin_queues
from .routes.admin import resources as admin_resources
from .routes.admin import roles as admin_roles
from .routes.admin import scheduler as admin_scheduler
from .routes.admin import smtp as admin_smtp
from .routes.admin import socketio_emit as admin_socketio_emit
from .routes.admin import stats as admin_stats
from .routes.admin import storage as admin_storage
from .routes.admin import tables as admin_tables
from .routes.admin import usage as admin_usage
from .routes.admin import user_storage as admin_user_storage
from .routes.admin import users as admin_users
from .routes.admin import viewers_config as admin_viewers_config
from .routes.bookings import bookings, planning, reservables
from .routes.domains import desktop_direct_viewer, desktops, templates

app.include_router(open_router)
app.include_router(token_router)
app.include_router(advanced_router)
app.include_router(manager_router)
app.include_router(admin_router)
app.include_router(maintenance_router)
app.include_router(register_router)
app.include_router(password_reset_router)
app.include_router(disclaimer_router)
app.include_router(direct_viewer_router)
app.include_router(migration_router)
app.include_router(email_verification_router)


@app.exception_handler(Error)
async def error_handler(request: Request, exception: Error):
    # Blank internal debug info before sending to client (OWASP A05). The
    # keys must remain in the body — `isardvdi_apiv4_client` and other
    # generated consumers decode `ErrorResponse` with strict `d.pop(field)`
    # and a missing key surfaces as a parse-time `KeyError` that hides the
    # real apiv4 error. `params` must also never be null because the
    # generated `ErrorResponse.params: ErrorResponseParams` decoder is not
    # null-safe.
    sensitive = {"debug", "request", "function", "function_call"}
    safe_error = {k: ("" if k in sensitive else v) for k, v in exception.error.items()}
    if safe_error.get("params") is None:
        safe_error["params"] = {}
    return JSONResponse(
        status_code=exception.status_code,
        content=safe_error,
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exception: ValueError):
    """Translate ``ValueError`` into a typed 404.

    ``RethinkBase.__init__`` raises ``ValueError("Document with id X
    does not exist.")`` whenever a model is constructed with a missing
    id. Without this handler every route's ``except Exception`` swallows
    that ValueError and re-wraps it as a generic 500 — the audit found
    this pattern across admin_categories.* and many other ``Category(id)``
    / ``Group(id)`` / ``Domain(id)`` callsites. Map it to a typed 404
    so the webapp / Vue frontends can surface a clean error toast.
    """
    return JSONResponse(
        status_code=404,
        content=_error_response_body(
            error="not_found",
            msg="Not found",
            description=str(exception),
        ),
    )


def _custom_openapi():
    """Apply gen_openapi strippers to the runtime OpenAPI schema.

    Ensures the schema served at ``/api/v4/openapi.json`` matches the
    codegen output at ``pkg/oas/apiv4/apiv4.json`` byte-for-byte
    (modulo ordering). Single source of truth: the strippers live in
    ``gen_openapi.py``; this override reuses them rather than
    duplicating the logic.
    """
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    from gen_openapi import (
        _normalize_operation_ids,
        _strip_colliding_component_titles,
        _strip_component_property_titles,
        _strip_null_unions,
        _strip_parameter_titles,
        _strip_path_inline_body_titles,
        _strip_path_parameter_anyof_null,
    )

    spec = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    _strip_path_parameter_anyof_null(spec)
    _strip_null_unions(spec)
    _strip_parameter_titles(spec)
    _strip_component_property_titles(spec)
    _strip_colliding_component_titles(spec)
    _strip_path_inline_body_titles(spec)
    _normalize_operation_ids(spec)
    app.openapi_schema = spec
    return spec


app.openapi = _custom_openapi
