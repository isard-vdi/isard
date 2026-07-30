# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminOperationsService hypervisor start/stop.

``start_hypervisor`` / ``stop_hypervisor`` are gRPC *mutations*
(``CreateHypervisor`` / ``DestroyHypervisor``). Memoizing them turns a
repeated admin action into a silent no-op that still reports success, so
every call has to reach the orchestrator.
"""

from unittest.mock import MagicMock

import pytest
from api.services.admin import operations as operations_service
from api.services.admin.operations import AdminOperationsService


class _FakeResponse:
    """Stand-in for the protobuf response: only ``state`` and ``msg`` are read."""

    def __init__(self, state: str, msg: str) -> None:
        self.state = state
        self.msg = msg


@pytest.fixture
def operations_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(operations_service, "_get_operations_client", lambda: client)
    return client


def test_start_hypervisor_issues_the_grpc_call_every_time(operations_client):
    operations_client.CreateHypervisor.side_effect = [
        _FakeResponse("AVAILABLE_TO_DESTROY", "first"),
        _FakeResponse("AVAILABLE_TO_DESTROY", "second"),
    ]

    first = AdminOperationsService.start_hypervisor("hyper-1")
    second = AdminOperationsService.start_hypervisor("hyper-1")

    assert operations_client.CreateHypervisor.call_count == 2
    assert first == {"state": "AVAILABLE_TO_DESTROY", "msg": "first"}
    assert second == {"state": "AVAILABLE_TO_DESTROY", "msg": "second"}


def test_stop_hypervisor_issues_the_grpc_call_every_time(operations_client):
    operations_client.DestroyHypervisor.side_effect = [
        _FakeResponse("AVAILABLE_TO_CREATE", "first"),
        _FakeResponse("AVAILABLE_TO_CREATE", "second"),
    ]

    first = AdminOperationsService.stop_hypervisor("hyper-1")
    second = AdminOperationsService.stop_hypervisor("hyper-1")

    assert operations_client.DestroyHypervisor.call_count == 2
    assert first == {"state": "AVAILABLE_TO_CREATE", "msg": "first"}
    assert second == {"state": "AVAILABLE_TO_CREATE", "msg": "second"}
