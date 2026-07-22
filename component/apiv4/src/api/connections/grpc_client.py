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
"""

import asyncio
import logging

import grpc
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2_grpc
from isardvdi_protobuf.operations.v1 import operations_pb2_grpc
from isardvdi_protobuf.sessions.v1 import sessions_pb2_grpc

log = logging.getLogger(__name__)


def _create_grpc_channel(host, port):
    return grpc.insecure_channel(
        f"{host}:{port}",
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.keepalive_permit_without_calls", True),
        ],
    )


def _create_grpc_client(stub, host, port):
    chan = _create_grpc_channel(host, port)
    return stub(chan)


def create_sessions_client(host, port):
    return _create_grpc_client(sessions_pb2_grpc.SessionsServiceStub, host, port)


def create_operations_client(host, port):
    return _create_grpc_client(operations_pb2_grpc.OperationsServiceStub, host, port)


def create_haproxy_bastion_client(host, port):
    return _create_grpc_client(haproxy_sync_pb2_grpc.HaproxySyncServiceStub, host, port)


def create_haproxy_sync_client(host, port):
    """Create haproxy sync client returning (stub, channel) for health watching."""
    chan = _create_grpc_channel(host, port)
    return haproxy_sync_pb2_grpc.HaproxySyncServiceStub(chan), chan


async def async_watch_health_check(channel, service_name, on_reconnect, interval=30):
    """Poll gRPC service health and call ``on_reconnect`` when it recovers.

    Periodically issues a unary ``Health.Check`` for ``service_name`` and
    invokes ``on_reconnect`` once each time the service transitions from
    not-serving (or unreachable) back to SERVING. The first observation only
    records state — it never fires ``on_reconnect`` — because startup already
    performs an initial sync.
    """
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    health_stub = health_pb2_grpc.HealthStub(channel)
    request = health_pb2.HealthCheckRequest(service=service_name)

    previously_serving = None

    while True:
        try:
            status = await asyncio.to_thread(
                lambda: health_stub.Check(request, timeout=5).status
            )
            serving = status == health_pb2.HealthCheckResponse.SERVING
            if serving and previously_serving is False:
                log.info(f"gRPC service {service_name} reconnected, syncing...")
                await asyncio.to_thread(on_reconnect)
            previously_serving = serving
        except grpc.RpcError as exc:
            if previously_serving is not False:
                log.warning(
                    f"gRPC health check failed for {service_name}: "
                    f"{exc.code().name}; will retry"
                )
            previously_serving = False
        except Exception:
            log.warning(f"Health check error for {service_name}", exc_info=True)
            previously_serving = False

        log.debug(
            f"gRPC health check for {service_name}: previously_serving={previously_serving}"
        )

        await asyncio.sleep(interval)
