import asyncio
import logging

import grpc
import grpc.experimental.gevent as grpc_gevent
from isardvdi_protobuf.haproxy_sync.v1 import haproxy_sync_pb2_grpc
from isardvdi_protobuf.operations.v1 import operations_pb2_grpc
from isardvdi_protobuf.sessions.v1 import sessions_pb2_grpc

grpc_gevent.init_gevent()

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


async def async_watch_health_check(channel, service_name, on_reconnect):
    """Watch gRPC service health and call on_reconnect when it transitions to SERVING.

    Async version of main's gevent-based watch_health_check. Runs sync gRPC
    health checks in a thread to avoid blocking the event loop.
    """
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    previous_status = None

    while True:
        try:
            health_stub = health_pb2_grpc.HealthStub(channel)
            request = health_pb2.HealthCheckRequest(service=service_name)

            def _watch_blocking():
                return list(health_stub.Watch(request, timeout=30))

            responses = await asyncio.to_thread(_watch_blocking)
            for response in responses:
                current_status = response.status
                if (
                    previous_status is not None
                    and previous_status != health_pb2.HealthCheckResponse.SERVING
                    and current_status == health_pb2.HealthCheckResponse.SERVING
                ):
                    log.info(f"gRPC service {service_name} reconnected, syncing...")
                    await asyncio.to_thread(on_reconnect)
                previous_status = current_status

        except grpc.RpcError:
            previous_status = None
            await asyncio.sleep(5)
        except Exception:
            log.warning(f"Health check error for {service_name}", exc_info=True)
            previous_status = None
            await asyncio.sleep(5)
