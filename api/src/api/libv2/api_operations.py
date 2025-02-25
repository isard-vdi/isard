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

import grpc
from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from operations.v1 import operations_pb2

from api import app

from .api_hypervisors import ApiHypervisors

api_hypervisors = ApiHypervisors()

# Mapping HypervisorState enum values to readable names
HYPERVISOR_STATE_MAP = {
    0: "UNSPECIFIED",
    1: "UNKNOWN",
    2: "AVAILABLE_TO_CREATE",
    3: "AVAILABLE_TO_DESTROY",
}


@cached(cache=TTLCache(maxsize=1, ttl=10))
def list_hypervisors():
    try:
        response = app.operations_client.ListHypervisors(
            operations_pb2.ListHypervisorsRequest()
        )
        operations_hypervisors = [
            {
                "id": hypervisor.id,
                "state": HYPERVISOR_STATE_MAP.get(hypervisor.state, "UNKNOWN"),
                "cpu": hypervisor.cpu,
                "ram": hypervisor.ram,
                "capabilities": list(hypervisor.capabilities),
                "gpus": list(hypervisor.gpus),
            }
            for hypervisor in response.hypervisors
        ]

        registered_hypervisors = api_hypervisors.get_orchestrator_hypervisors()

        # Merge the two lists
        hypervisors = []
        for operations_hyper in operations_hypervisors:
            registered_hyper = next(
                (
                    rh
                    for rh in registered_hypervisors
                    if rh["id"] == operations_hyper["id"]
                ),
                None,
            )

            hypervisors.append(
                {
                    "id": operations_hyper["id"],
                    "state": operations_hyper["state"],
                    "isard_state": (
                        registered_hyper["status"] if registered_hyper else "-"
                    ),
                    "orchestrator_managed": (
                        registered_hyper["orchestrator_managed"]
                        if registered_hyper
                        else "-"
                    ),
                    "only_forced": (
                        registered_hyper["only_forced"] if registered_hyper else "-"
                    ),
                    "buffering_hyper": (
                        registered_hyper["buffering_hyper"] if registered_hyper else "-"
                    ),
                    "destroy_time": (
                        registered_hyper["destroy_time"] if registered_hyper else "-"
                    ),
                    "only_forced": (
                        registered_hyper["only_forced"] if registered_hyper else "-"
                    ),
                    "gpu_only": (
                        registered_hyper["gpu_only"] if registered_hyper else "-"
                    ),
                    "desktops_started": (
                        registered_hyper["desktops_started"]
                        if registered_hyper
                        else "-"
                    ),
                    "cpu": operations_hyper["cpu"],
                    "ram": operations_hyper["ram"],
                    "capabilities": operations_hyper["capabilities"],
                    "gpus": operations_hyper["gpus"],
                    "destroy_allowed": (
                        True
                        if registered_hyper
                        and registered_hyper["desktops_started"] == 0
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


@cached(cache=TTLCache(maxsize=20, ttl=10))
def start_hypervisor(hypervisor_id):
    try:
        response = app.operations_client.CreateHypervisor(
            operations_pb2.CreateHypervisorRequest(id=hypervisor_id)
        )
        return response.state, response.msg

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.UNAUTHENTICATED,
        ]:
            raise Error("unauthorized", "Not authorized")

        raise Error("internal_server", "Internal server error")


@cached(cache=TTLCache(maxsize=20, ttl=10))
def stop_hypervisor(hypervisor_id):
    try:
        response = app.operations_client.DestroyHypervisor(
            operations_pb2.DestroyHypervisorRequest(id=hypervisor_id)
        )
        return response.state, response.msg

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.UNAUTHENTICATED,
        ]:
            raise Error("unauthorized", "Not authorized")

        raise Error("internal_server", "Internal server error")
