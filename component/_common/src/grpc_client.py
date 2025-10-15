import grpc
import grpc.experimental.gevent as grpc_gevent
from haproxy.v1 import haproxy_pb2_grpc
from operations.v1 import operations_pb2_grpc
from sessions.v1 import sessions_pb2_grpc

grpc_gevent.init_gevent()


def _create_grpc_client(stub, host, port):
    chan = grpc.insecure_channel(
        f"{host}:{port}",
        options=[
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
        ],
    )
    return stub(chan)


def create_sessions_client(host, port):
    return _create_grpc_client(sessions_pb2_grpc.SessionsServiceStub, host, port)


def create_operations_client(host, port):
    return _create_grpc_client(operations_pb2_grpc.OperationsServiceStub, host, port)


def create_haproxy_bastion_client(host, port):
    return _create_grpc_client(haproxy_pb2_grpc.HaproxyBastionServiceStub, host, port)
