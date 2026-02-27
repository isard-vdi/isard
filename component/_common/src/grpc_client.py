import grpc
import grpc.experimental.gevent as grpc_gevent
from grpc_health.v1 import health_pb2, health_pb2_grpc
from haproxy_sync.v1 import haproxy_sync_pb2_grpc
from operations.v1 import operations_pb2_grpc
from sessions.v1 import sessions_pb2_grpc

grpc_gevent.init_gevent()


def _create_grpc_channel(host, port):
    return grpc.insecure_channel(
        f"{host}:{port}",
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
        ],
    )


def _create_grpc_client(stub, host, port):
    chan = _create_grpc_channel(host, port)
    return stub(chan)


def create_sessions_client(host, port):
    return _create_grpc_client(sessions_pb2_grpc.SessionsServiceStub, host, port)


def create_operations_client(host, port):
    return _create_grpc_client(operations_pb2_grpc.OperationsServiceStub, host, port)


def create_haproxy_sync_client(host, port):
    chan = _create_grpc_channel(host, port)
    return haproxy_sync_pb2_grpc.HaproxySyncServiceStub(chan), chan


def watch_health_check(chan, service_name, on_reconnect):
    """
    Watch the health check status of a gRPC service.
    Calls on_reconnect callback when service transitions to SERVING state.

    Args:
        chan: The gRPC channel to use
        service_name: The name of the service to watch (e.g., "haproxy_sync.v1.HaproxySyncService")
        on_reconnect: Callback function called when service reconnects (transitions to SERVING)
    """
    import gevent

    def _watch():
        previous_status = None
        health_stub = health_pb2_grpc.HealthStub(chan)

        while True:
            try:
                request = health_pb2.HealthCheckRequest(service=service_name)
                for response in health_stub.Watch(request):
                    current_status = response.status

                    if (
                        previous_status is not None
                        and previous_status != health_pb2.HealthCheckResponse.SERVING
                        and current_status == health_pb2.HealthCheckResponse.SERVING
                    ):
                        on_reconnect()

                    previous_status = current_status

            except grpc.RpcError:
                previous_status = health_pb2.HealthCheckResponse.NOT_SERVING
                gevent.sleep(5)
            except Exception:
                previous_status = health_pb2.HealthCheckResponse.NOT_SERVING
                gevent.sleep(5)

    gevent.spawn(_watch)
