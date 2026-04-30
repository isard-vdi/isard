#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.operations`.

Covers the ``/admin/operations/hypervisor*`` handlers that replaced
T1/operations v3_compat shims. Every route is gated on
``AdminOperationsService.is_operations_api_enabled()`` — tests
monkeypatch that to ``True`` to exercise the happy path.
"""

from api.routes.tests.helpers import MockJWT


def test_admin_operations_hypervisors_list(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "hyper-1", "state": "running"}]
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.is_operations_api_enabled",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.list_hypervisors",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/operations/hypervisors", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_operations_hypervisors_disabled_is_forbidden(monkeypatch, test_client):
    """If the operations API is disabled, the route must return 403."""
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.is_operations_api_enabled",
        staticmethod(lambda: False),
    )

    response = test_client(url="/admin/operations/hypervisors", jwt=jwt)

    assert response.status_code == 403


def test_admin_operations_hypervisor_start(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.is_operations_api_enabled",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.start_hypervisor",
        staticmethod(
            lambda hyper_id: calls.append(hyper_id)
            or {"id": hyper_id, "state": "starting"}
        ),
    )

    response = test_client(
        url="/admin/operations/hypervisor/hyper-1",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["hyper-1"]


def test_admin_operations_hypervisor_stop(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.is_operations_api_enabled",
        staticmethod(lambda: True),
    )
    monkeypatch.setattr(
        "api.services.admin.operations.AdminOperationsService.stop_hypervisor",
        staticmethod(
            lambda hyper_id: calls.append(hyper_id)
            or {"id": hyper_id, "state": "stopping"}
        ),
    )

    response = test_client(
        url="/admin/operations/hypervisor/hyper-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["hyper-1"]
