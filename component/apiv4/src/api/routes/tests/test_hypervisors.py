#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.hypervisors`.

Covers the admin hypervisor endpoints that replaced T1/hypervisor,
T1/hypervisors and T1/orchestrator v3_compat shims. All handlers live
on ``admin_router`` so the default ``MockJWT()`` (admin role) is
enough. Service-level calls are monkeypatched so no real DB is hit.
"""

from datetime import datetime, timezone

from api.routes.tests.helpers import MockJWT


def test_admin_hypervisors_list(monkeypatch, test_client):
    jwt = MockJWT()

    def _hypervisor(hyper_id, status, enabled):
        return {
            "id": hyper_id,
            "hostname": f"{hyper_id}.local",
            "port": "22",
            "description": "",
            "capabilities": {"disk_operations": True, "hypervisor": True},
            "only_forced": False,
            "min_free_mem_gb": 0,
            "min_free_gpu_mem_gb": 0,
            "nvidia_enabled": False,
            "force_get_hyp_info": False,
            "buffering_hyper": False,
            "gpu_only": False,
            "isard_hyper_vpn_host": "",
            "status": status,
            "enabled": enabled,
        }

    stub = [
        _hypervisor("hyper-1", "Online", True),
        _hypervisor("hyper-2", "Offline", False),
    ]
    captured = {}

    def fake_get_hypervisors(status=None):
        captured["status"] = status
        return stub

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hypervisors",
        staticmethod(fake_get_hypervisors),
    )

    response = test_client(url="/admin/items/hypervisors", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert [h["id"] for h in body] == ["hyper-1", "hyper-2"]
    assert captured["status"] is None


def test_admin_hypervisors_list_by_status(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_get_hypervisors(status=None):
        captured["status"] = status
        return []

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hypervisors",
        staticmethod(fake_get_hypervisors),
    )

    response = test_client(url="/admin/items/hypervisors/Online", jwt=jwt)

    assert response.status_code == 200
    assert captured == {"status": "Online"}


def test_admin_hypervisor_create(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(data):
        captured["hyper_id"] = data["hyper_id"]
        captured["hostname"] = data["hostname"]
        return {"id": data["hyper_id"], "status": "Offline"}

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.create_or_update_hypervisor",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/item/hypervisor",
        method="POST",
        body={
            "hyper_id": "hyper-new",
            "hostname": "hyper-new.internal",
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "hyper-new", "status": "Offline"}
    assert captured == {"hyper_id": "hyper-new", "hostname": "hyper-new.internal"}


def test_admin_hypervisor_enable(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_enable(hyper_id, enabled):
        captured["hyper_id"] = hyper_id
        captured["enabled"] = enabled
        return {"id": hyper_id, "enabled": enabled}

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.enable_hyper",
        staticmethod(fake_enable),
    )

    response = test_client(
        url="/admin/item/hypervisor/hyper-1",
        method="PUT",
        body={"enabled": False},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"hyper_id": "hyper-1", "enabled": False}


def test_admin_hypervisor_delete(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.remove_hyper",
        staticmethod(lambda hyper_id: calls.append(hyper_id) or {"removed": hyper_id}),
    )

    response = test_client(
        url="/admin/item/hypervisor/hyper-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["hyper-1"]


def test_admin_hypervisor_stop_domains(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.stop_hyper_domains",
        staticmethod(lambda hyper_id: calls.append(hyper_id)),
    )

    response = test_client(
        url="/admin/item/hypervisor/stop/hyper-1",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["hyper-1"]


def test_admin_hypervisor_virt_pools_get(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "pool-1", "enabled": True}]
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hyper_virt_pools",
        staticmethod(lambda hyper_id: stub),
    )

    response = test_client(url="/admin/items/hypervisor/hyper-1/virt_pools", jwt=jwt)

    # ``response_model=list[AdminHypervisorVirtPool]`` adds the
    # declared optional ``name`` field with a None default; per-key
    # asserts replace equality on the partial stub.
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "pool-1"
    assert body[0]["enabled"] is True


def test_admin_hypervisor_virt_pools_update(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_update(hyper_id, data):
        captured["hyper_id"] = hyper_id
        captured["id"] = data["id"]
        captured["enable_virt_pool"] = data["enable_virt_pool"]

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.update_hyper_virt_pools",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/admin/items/hypervisor/hyper-1/virt_pools",
        method="PUT",
        body={"id": "pool-1", "enable_virt_pool": True},
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured == {
        "hyper_id": "hyper-1",
        "id": "pool-1",
        "enable_virt_pool": True,
    }


def test_admin_hypervisor_mountpoints(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"path": "/isard", "size": 1000000}]
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hyper_mountpoints",
        staticmethod(lambda hyper_id: stub),
    )

    response = test_client(url="/admin/items/hypervisor/mountpoints/hyper-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_hypervisor_started_domains(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "desktop-1", "user_name": "alice"}]
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hyper_started_domains",
        staticmethod(lambda hyper_id: stub),
    )

    response = test_client(
        url="/admin/items/hypervisor/started_domains/hyper-1", jwt=jwt
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "desktop-1"
    assert body[0].get("user_name") == "alice"


# ─── Orchestrator hypervisor management (T1/orchestrator shims) ─────────


def test_admin_orchestrator_managed_list(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {
            "id": "hyper-1",
            "status": "Online",
            "destroy_time": "2026-07-20T13:00:00+00:00",
        }
    ]
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_orchestrator_managed_hypervisors",
        staticmethod(lambda: stub),
    )

    response = test_client(
        url="/admin/items/hypervisors/orchestrator_managed",
        method="POST",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == "hyper-1"
    assert body[0]["status"] == "Online"
    parsed = datetime.fromisoformat(body[0]["destroy_time"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 7, 20, 13, 0, 0, tzinfo=timezone.utc)


def test_admin_orchestrator_hypervisors_list_dates_roundtrip(monkeypatch, test_client):
    """The orchestrator (Go) consumes these dates as ``time.Time`` via the
    generated client; the wire values are the tz-aware isoformat strings
    written by ``isardvdi_common``. Pin that a stub row round-trips to an
    ISO-8601 tz-aware value and that absent dates stay null/absent."""
    jwt = MockJWT()
    stub = [
        {
            "id": "hyper-1",
            "status": "Online",
            "destroy_time": "2026-07-20T13:00:00+00:00",
            "bookings_end_time": "2026-07-21T09:30:00+00:00",
        },
        {"id": "hyper-2", "status": "Offline"},
    ]
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_orchestrator_hypervisors",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/items/orchestrator/hypervisors", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    h1 = next(h for h in body if h["id"] == "hyper-1")
    for field, expected in (
        ("destroy_time", datetime(2026, 7, 20, 13, 0, 0, tzinfo=timezone.utc)),
        ("bookings_end_time", datetime(2026, 7, 21, 9, 30, 0, tzinfo=timezone.utc)),
    ):
        parsed = datetime.fromisoformat(h1[field].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None, f"{field} must be tz-aware"
        assert parsed == expected
    h2 = next(h for h in body if h["id"] == "hyper-2")
    assert h2.get("destroy_time") is None
    assert h2.get("bookings_end_time") is None


def test_admin_orchestrator_manage_unset(monkeypatch, test_client):
    """DELETE /admin/orchestrator/hypervisor/{id}/manage — replaces the
    webapp's T1/orchestrator DELETE .../manage shim."""
    jwt = MockJWT()
    captured = {}

    def fake_set(hyper_id, reset=False):
        captured["hyper_id"] = hyper_id
        captured["reset"] = reset

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.set_hyper_orchestrator_managed",
        staticmethod(fake_set),
    )

    response = test_client(
        url="/admin/item/orchestrator/hypervisor/hyper-1/manage",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured == {"hyper_id": "hyper-1", "reset": True}


def test_admin_orchestrator_manage_set(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set(hyper_id, reset=False):
        captured["hyper_id"] = hyper_id
        captured["reset"] = reset

    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.set_hyper_orchestrator_managed",
        staticmethod(fake_set),
    )

    response = test_client(
        url="/admin/item/orchestrator/hypervisor/hyper-1/manage",
        method="POST",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured == {"hyper_id": "hyper-1", "reset": False}


# ─── POST /admin/vlans (Category A3) ─────────────────────────────────────


def test_admin_register_vlans_happy_path(test_client):
    """Typed body ``AdminRegisterVlansRequest`` now replaces the
    hand-rolled ``data.get("vlans", [])`` read. The handler upserts
    one ``interfaces`` row per VLAN id into RethinkDB — the mock
    connection in the ``test_client`` fixture captures the writes.
    """
    jwt = MockJWT()

    response = test_client(
        url="/admin/items/vlans",
        method="POST",
        body={"vlans": ["100", "200"]},
        jwt=jwt,
        db_tables_data={"interfaces": []},
    )

    assert response.status_code == 204


def test_admin_register_vlans_empty_list(test_client):
    """Empty ``vlans`` list is accepted as a no-op. Pins semantics so a
    future ``min_items=1`` tightening becomes a deliberate breaking
    change rather than a silent drift."""
    jwt = MockJWT()

    response = test_client(
        url="/admin/items/vlans",
        method="POST",
        body={"vlans": []},
        jwt=jwt,
        db_tables_data={"interfaces": []},
    )

    assert response.status_code == 204


def test_admin_register_vlans_rejects_missing_field(test_client):
    jwt = MockJWT()

    response = test_client(
        url="/admin/items/vlans",
        method="POST",
        body={"not_vlans": ["100"]},
        jwt=jwt,
        db_tables_data={"interfaces": []},
    )

    # apiv4 installs a RequestValidationError handler that reshapes
    # FastAPI's default 422 into the legacy 400 envelope.
    assert response.status_code == 400


# ─── PUT /admin/hypervisor/{hyper_id}/boot_progress (Category A4) ────────


def test_admin_hypervisor_boot_progress_happy_path(test_client):
    """Typed body ``AdminBootProgressRequest``. ``boot_progress`` is a
    structured dict (``{step, total, label, error, timestamp}``); the
    hypervisor caller (``docker/hypervisor/src/lib/progress.py``) now
    sends the decoded object directly (previously json.dumps'd).
    """
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/boot_progress",
        method="PUT",
        body={
            "boot_progress": {
                "step": 2,
                "total": 5,
                "label": "libvirt",
                "error": None,
                "timestamp": 1700000000,
            }
        },
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
    )

    assert response.status_code == 204


def test_admin_hypervisor_boot_progress_rejects_string_payload(test_client):
    """Encoded-string payloads are no longer accepted: the schema
    tightened to ``Dict[str, Any]`` after migrating ``progress.py`` off
    ``json.dumps``. Pins the contract."""
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/boot_progress",
        method="PUT",
        body={"boot_progress": '{"step": 1}'},
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
    )

    assert response.status_code == 400


def test_admin_hypervisor_boot_progress_rejects_missing_field(test_client):
    jwt = MockJWT()

    response = test_client(
        url="/admin/item/hypervisor/hyper-1/boot_progress",
        method="PUT",
        body={"other": 1},
        jwt=jwt,
        db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
    )

    # apiv4 installs a RequestValidationError handler that reshapes
    # FastAPI's default 422 into the legacy 400 envelope.
    assert response.status_code == 400
