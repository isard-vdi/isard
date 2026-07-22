#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import os
import traceback
from typing import TYPE_CHECKING

from api.services.error import Error
from cachetools import cached
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache

if TYPE_CHECKING:
    from isardvdi_protobuf.operations.v1.operations_pb2_grpc import (
        OperationsServiceStub,
    )

# Named caches: 10 s TTL is mainly thundering-herd protection on the
# orchestrator gRPC, so writers don't normally need to invalidate, but
# keeping them named lets tests clear between cases.
list_hypervisors_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=1, ttl=10)
start_hypervisor_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=20, ttl=10)
stop_hypervisor_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=20, ttl=10)


def clear_admin_operations_caches() -> None:
    """Clear all admin operations caches at once."""
    list_hypervisors_cache.clear()
    start_hypervisor_cache.clear()
    stop_hypervisor_cache.clear()


class AdminOperationsService:
    """Service for admin operations (hypervisor orchestration via gRPC)."""

    @staticmethod
    def is_operations_api_enabled() -> bool:
        """Check if the operations API is enabled."""
        enabled = os.getenv("OPERATIONS_API_ENABLED")
        if enabled is None:
            return False
        return enabled.lower() == "true"

    @staticmethod
    @cached(cache=list_hypervisors_cache)
    def list_hypervisors() -> list:
        """List hypervisors via operations gRPC."""
        import grpc
        from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed
        from isardvdi_protobuf.operations.v1 import operations_pb2

        try:
            # Get gRPC client
            from api.services.admin.operations import _get_operations_client

            client = _get_operations_client()
            response = client.ListHypervisors(operations_pb2.ListHypervisorsRequest())
            operations_hypervisors = [
                {
                    "id": hypervisor.id,
                    "state": _HYPERVISOR_STATE_MAP.get(hypervisor.state, "UNKNOWN"),
                    "cpu": hypervisor.cpu,
                    "ram": hypervisor.ram,
                    "capabilities": list(hypervisor.capabilities),
                    "gpus": list(hypervisor.gpus),
                }
                for hypervisor in response.hypervisors
            ]

            registered_hypervisors = HypervisorsProcessed.get_orchestrator_hypervisors()

            hypervisors = []
            for op_hyper in operations_hypervisors:
                reg_hyper = next(
                    (rh for rh in registered_hypervisors if rh["id"] == op_hyper["id"]),
                    None,
                )
                hypervisors.append(
                    {
                        "id": op_hyper["id"],
                        "state": op_hyper["state"],
                        "isard_state": (reg_hyper["status"] if reg_hyper else "-"),
                        "orchestrator_managed": (
                            reg_hyper["orchestrator_managed"] if reg_hyper else "-"
                        ),
                        "only_forced": (reg_hyper["only_forced"] if reg_hyper else "-"),
                        "buffering_hyper": (
                            reg_hyper["buffering_hyper"] if reg_hyper else "-"
                        ),
                        "destroy_time": (
                            reg_hyper["destroy_time"] if reg_hyper else "-"
                        ),
                        "gpu_only": (reg_hyper["gpu_only"] if reg_hyper else "-"),
                        "desktops_started": (
                            reg_hyper["desktops_started"] if reg_hyper else "-"
                        ),
                        "cpu": op_hyper["cpu"],
                        "ram": op_hyper["ram"],
                        "capabilities": op_hyper["capabilities"],
                        "gpus": op_hyper["gpus"],
                        "destroy_allowed": (
                            True
                            if reg_hyper and reg_hyper["desktops_started"] == 0
                            else False
                        ),
                    }
                )
            return hypervisors

        except grpc.RpcError as rpc_error:
            if rpc_error.code() in [
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.UNAUTHENTICATED,
            ]:
                raise Error("unauthorized", "Not authorized")
            raise Error("internal_server", "Internal server error")

    @staticmethod
    @cached(cache=start_hypervisor_cache)
    def start_hypervisor(hypervisor_id: str) -> dict:
        """Start a hypervisor via operations gRPC."""
        import grpc
        from isardvdi_protobuf.operations.v1 import operations_pb2

        try:
            client = _get_operations_client()
            response = client.CreateHypervisor(
                operations_pb2.CreateHypervisorRequest(id=hypervisor_id)
            )
            return {"state": response.state, "msg": response.msg}

        except grpc.RpcError as rpc_error:
            if rpc_error.code() in [
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.UNAUTHENTICATED,
            ]:
                raise Error("unauthorized", "Not authorized")
            raise Error("internal_server", "Internal server error")

    @staticmethod
    @cached(cache=stop_hypervisor_cache)
    def stop_hypervisor(hypervisor_id: str) -> dict:
        """Stop a hypervisor via operations gRPC."""
        import grpc
        from isardvdi_protobuf.operations.v1 import operations_pb2

        try:
            client = _get_operations_client()
            response = client.DestroyHypervisor(
                operations_pb2.DestroyHypervisorRequest(id=hypervisor_id)
            )
            return {"state": response.state, "msg": response.msg}

        except grpc.RpcError as rpc_error:
            if rpc_error.code() in [
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.UNAUTHENTICATED,
            ]:
                raise Error("unauthorized", "Not authorized")
            raise Error("internal_server", "Internal server error")


# Mapping HypervisorState enum values to readable names
_HYPERVISOR_STATE_MAP = {
    0: "UNSPECIFIED",
    1: "UNKNOWN",
    2: "AVAILABLE_TO_CREATE",
    3: "AVAILABLE_TO_DESTROY",
}


def _get_operations_client() -> "OperationsServiceStub":
    """Get or create operations gRPC client."""
    from api.connections.grpc_client import create_operations_client

    host = os.environ.get("OPERATIONS_HOST", "isard-operations")
    port = os.environ.get("OPERATIONS_PORT", "1312")
    return create_operations_client(host, port)
