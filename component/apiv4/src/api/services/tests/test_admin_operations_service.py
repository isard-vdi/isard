# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminOperationsService hypervisor start/stop.

``start_hypervisor`` / ``stop_hypervisor`` are gRPC *mutations*
(``CreateHypervisor`` / ``DestroyHypervisor``). Memoizing them turns a
repeated admin action into a silent no-op that still reports success, so
every call has to reach the orchestrator.

Both RPCs are declared ``returns (stream ...)`` in
``pkg/proto/operations/v1/operations.proto``: the stub hands back an
iterator of progress messages, not a single response. Treating it as
unary raises ``AttributeError`` and drops the stream, which cancels the
in-flight operation on the orchestrator.
"""

from unittest.mock import MagicMock

import pytest
from api.schemas.admin.operations import HypervisorActionResponse
from api.services.admin import operations as operations_service
from api.services.admin.operations import AdminOperationsService
from isardvdi_protobuf.operations.v1 import operations_pb2


def _create_stream(*messages):
    """A server-streaming ``CreateHypervisor`` reply, as a one-shot iterator."""
    return iter(
        [
            operations_pb2.CreateHypervisorResponse(state=state, msg=msg)
            for state, msg in messages
        ]
    )


def _destroy_stream(*messages):
    """A server-streaming ``DestroyHypervisor`` reply, as a one-shot iterator."""
    return iter(
        [
            operations_pb2.DestroyHypervisorResponse(state=state, msg=msg)
            for state, msg in messages
        ]
    )


_SCHEDULED = operations_pb2.OperationState.OPERATION_STATE_SCHEDULED
_ACTIVE = operations_pb2.OperationState.OPERATION_STATE_ACTIVE
_FAILED = operations_pb2.OperationState.OPERATION_STATE_FAILED
_COMPLETED = operations_pb2.OperationState.OPERATION_STATE_COMPLETED


@pytest.fixture
def operations_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(operations_service, "_get_operations_client", lambda: client)
    return client


def test_start_hypervisor_issues_the_grpc_call_every_time(operations_client):
    operations_client.CreateHypervisor.side_effect = [
        _create_stream((_COMPLETED, "first")),
        _create_stream((_COMPLETED, "second")),
    ]

    first = AdminOperationsService.start_hypervisor("hyper-1")
    second = AdminOperationsService.start_hypervisor("hyper-1")

    assert operations_client.CreateHypervisor.call_count == 2
    assert first == {"state": "OPERATION_STATE_COMPLETED", "msg": "first"}
    assert second == {"state": "OPERATION_STATE_COMPLETED", "msg": "second"}


def test_stop_hypervisor_issues_the_grpc_call_every_time(operations_client):
    operations_client.DestroyHypervisor.side_effect = [
        _destroy_stream((_COMPLETED, "first")),
        _destroy_stream((_COMPLETED, "second")),
    ]

    first = AdminOperationsService.stop_hypervisor("hyper-1")
    second = AdminOperationsService.stop_hypervisor("hyper-1")

    assert operations_client.DestroyHypervisor.call_count == 2
    assert first == {"state": "OPERATION_STATE_COMPLETED", "msg": "first"}
    assert second == {"state": "OPERATION_STATE_COMPLETED", "msg": "second"}


def test_start_hypervisor_reports_the_last_streamed_message(operations_client):
    operations_client.CreateHypervisor.return_value = _create_stream(
        (_SCHEDULED, "queued"),
        (_ACTIVE, "booting"),
        (_COMPLETED, "hypervisor ready"),
    )

    assert AdminOperationsService.start_hypervisor("hyper-1") == {
        "state": "OPERATION_STATE_COMPLETED",
        "msg": "hypervisor ready",
    }


def test_stop_hypervisor_reports_the_last_streamed_message(operations_client):
    operations_client.DestroyHypervisor.return_value = _destroy_stream(
        (_SCHEDULED, "queued"),
        (_ACTIVE, "draining"),
        (_FAILED, "hypervisor still has desktops"),
    )

    assert AdminOperationsService.stop_hypervisor("hyper-1") == {
        "state": "OPERATION_STATE_FAILED",
        "msg": "hypervisor still has desktops",
    }


def test_stop_hypervisor_drains_the_whole_stream(operations_client):
    """Returning before the stream ends cancels the RPC, and the
    orchestrator aborts the destroy it had already started."""
    consumed = []

    def stream():
        for state, msg in (
            (_SCHEDULED, "queued"),
            (_ACTIVE, "draining"),
            (_COMPLETED, "destroyed"),
        ):
            consumed.append(msg)
            yield operations_pb2.DestroyHypervisorResponse(state=state, msg=msg)

    operations_client.DestroyHypervisor.return_value = stream()

    AdminOperationsService.stop_hypervisor("hyper-1")

    assert consumed == ["queued", "draining", "destroyed"]


def test_start_hypervisor_returns_an_empty_result_when_nothing_is_streamed(
    operations_client,
):
    operations_client.CreateHypervisor.return_value = _create_stream()

    assert AdminOperationsService.start_hypervisor("hyper-1") == {
        "state": None,
        "msg": None,
    }


@pytest.mark.parametrize("action", ["start_hypervisor", "stop_hypervisor"])
def test_result_validates_against_the_route_response_model(operations_client, action):
    """``state`` reaches the route as the protobuf enum name: the raw int
    the stub yields fails ``HypervisorActionResponse`` validation and the
    admin gets a 500 instead of the operation result."""
    operations_client.CreateHypervisor.return_value = _create_stream(
        (_COMPLETED, "done")
    )
    operations_client.DestroyHypervisor.return_value = _destroy_stream(
        (_COMPLETED, "done")
    )

    result = getattr(AdminOperationsService, action)("hyper-1")

    assert HypervisorActionResponse(**result).state == "OPERATION_STATE_COMPLETED"
