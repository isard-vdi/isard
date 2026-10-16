"""gRPC client factories for apiv4.

apiv4 is the only service in the monorepo that actually exercises these
factories at runtime — sessions auth on every request, haproxy-sync at
startup + reconnect-watcher, operations and bastion on admin paths.
Other services (engine, webapp, notifier, change-handler) import the
``isardvdi_common`` modules that *thread* gRPC types through their
return values but never reach the network — those modules now wire in
their backends via ``configure_*_client`` providers (see
``isardvdi_common.connections.api_sessions``,
``isardvdi_common.helpers.bastion``, ``isardvdi_common.models.targets``).

This module previously lived under ``isardvdi_common.connections`` and
contained an unconditional ``grpc.experimental.gevent.init_gevent()``
call at import time. That call patched gRPC's C-level event poller to
dispatch through gevent's libev hub. Per upstream's own docstring:

    "This must be called AFTER the python standard lib has been
    patched [via gevent.monkey.patch_all()], but BEFORE creating any
    gRPC objects."

apiv4 (FastAPI on uvicorn / asyncio) does not call ``monkey.patch_all``
— and shouldn't, because gevent's cooperative I/O model is mutually
exclusive with asyncio's event loop. So the precondition was never
satisfied. Under concurrent load (multiple worker threads in
``asyncio.to_thread`` calling sessions/bastion/haproxy-sync clients
through a half-initialised gevent hub) the C extension corrupted its
own state and SIGSEGV'd in ``corecext.cpython-313-...so``. Two
documented incidents: 2026-05-01 (43-min outage during k6+e2e load)
and 2026-05-05 17:59:55 (kernel-logged segfault, 45-min hang until
manual restart). The misuse and the crash are the same root cause.

The fix: keep the gRPC client factories sync (the Python sync API runs
fine on uvicorn worker threads via ``asyncio.to_thread``) and never
touch gevent. If a future Flask+gevent service needs gRPC clients from
here, route them through that service's own bootstrap (after its own
``monkey.patch_all``), not through this module — a shared library
cannot know whether its importer is monkey-patched, and guessing wrong
is fatal.

The one exception is the resync watcher, which uses gRPC's asyncio API.
Every other client here is consumed from worker threads via
``asyncio.to_thread``, where blocking is harmless; the watcher is the
only one that lives *on* the event loop, and the ``WatchResync`` RPC
it consumes is a server stream that stays silent while the service is
healthy — a sync iterator over it blocks in C until the next resync
push, pinning the loop thread and hanging uvicorn (its signal handlers
are loop callbacks). Per ``grpc/aio/__init__.py``, aio objects may only
be used on the thread that created them, so the aio channel and its
stub must never be touched from a worker thread.
"""

import asyncio
import logging

import grpc
import grpc.aio
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2, haproxy_sync_pb2_grpc
from isardvdi_protobuf.operations.v1 import operations_pb2_grpc
from isardvdi_protobuf.sessions.v1 import sessions_pb2_grpc

log = logging.getLogger(__name__)

_GRPC_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 10000),
    ("grpc.keepalive_timeout_ms", 5000),
    ("grpc.keepalive_permit_without_calls", True),
]


def _create_grpc_channel(host, port):
    return grpc.insecure_channel(f"{host}:{port}", options=_GRPC_CHANNEL_OPTIONS)


def _create_grpc_client(stub, host, port):
    chan = _create_grpc_channel(host, port)
    return stub(chan)


def create_sessions_client(host, port):
    return _create_grpc_client(sessions_pb2_grpc.SessionsServiceStub, host, port)


def create_operations_client(host, port):
    return _create_grpc_client(operations_pb2_grpc.OperationsServiceStub, host, port)


def create_haproxy_bastion_client(host, port):
    return _create_grpc_client(haproxy_sync_pb2_grpc.HaproxySyncServiceStub, host, port)


def create_resync_watch_channel(host, port):
    """Create an *asyncio* gRPC channel for `async_watch_resync`."""
    return grpc.aio.insecure_channel(f"{host}:{port}", options=_GRPC_CHANNEL_OPTIONS)


async def async_watch_resync(channel, on_resync, max_backoff=30):
    """Call `on_resync(reason)` per haproxy-sync `WatchResync` request and report its outcome."""
    stub = haproxy_sync_pb2_grpc.HaproxySyncServiceStub(channel)
    backoff = 1

    while True:
        try:
            call = stub.WatchResync(haproxy_sync_pb2.WatchResyncRequest())
            try:
                async for message in call:
                    backoff = 1
                    log.info(
                        f"haproxy-sync asked for a resync: {message.reason} "
                        f"(request {message.id})"
                    )
                    error = ""
                    try:
                        await asyncio.to_thread(on_resync, message.reason)
                    except Exception as exc:
                        error = str(exc) or type(exc).__name__
                        log.warning(
                            f"HAProxy resync failed (reason: {message.reason}, "
                            f"request {message.id}), haproxy-sync will ask again",
                            exc_info=True,
                        )
                    try:
                        await stub.AckResync(
                            haproxy_sync_pb2.AckResyncRequest(
                                id=message.id, error=error
                            ),
                            timeout=10,
                        )
                    except grpc.RpcError as exc:
                        log.warning(
                            f"Could not report HAProxy resync request {message.id}: "
                            f"{exc.code().name}"
                        )
            finally:
                call.cancel()
            log.warning("haproxy-sync resync stream ended, reconnecting")
        except grpc.RpcError as exc:
            log.warning(
                f"haproxy-sync resync stream failed: {exc.code().name}; "
                f"retrying in {backoff}s"
            )
        except Exception:
            log.warning("haproxy-sync resync stream error", exc_info=True)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
