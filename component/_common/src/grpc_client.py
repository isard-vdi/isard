import grpc
import grpc.experimental.gevent as grpc_gevent
from operations.v1 import operations_pb2_grpc
from sessions.v1 import sessions_pb2_grpc

grpc_gevent.init_gevent()


def _create_grpc_client(stub, host, port):
    chan = grpc.insecure_channel(f"{host}:{port}")
    return stub(chan)


def create_sessions_client(host, port):
    return _create_grpc_client(sessions_pb2_grpc.SessionsServiceStub, host, port)


def create_operations_client(host, port):
    return _create_grpc_client(operations_pb2_grpc.OperationsServiceStub, host, port)
