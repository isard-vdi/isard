#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.domains`.

Covers a representative subset of the admin domains endpoints used by
the webapp admin: domain details, viewer_data, storage, and domains
by status. The routes are manager-level; the default ``MockJWT()``
(admin) satisfies the ``is_admin_or_manager`` dependency.
"""

from api.routes.tests.helpers import MockJWT


def test_admin_domain_details(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "id": "desktop-1",
        "name": "Desktop 1",
        "status": "Stopped",
        "user": "user-1",
    }
    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.get_domain_details",
        staticmethod(lambda payload, domain_id: stub),
    )

    response = test_client(url="/admin/domain/desktop-1/details", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_domain_viewer_data(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"viewers": {"browser-vnc": {"url": "https://viewer.example/vnc/1"}}}
    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.get_domain_viewer_data",
        staticmethod(lambda payload, domain_id: stub),
    )

    response = test_client(url="/admin/domain/desktop-1/viewer_data", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_domain_storage(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "stor-1", "size": 10737418240, "status": "ready"}]
    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.get_domain_storage",
        staticmethod(lambda payload, domain_id: stub),
    )

    response = test_client(url="/admin/domain/storage/desktop-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_domains_by_status(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "desktop-1", "status": "Failed"}]
    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.get_domains_by_status",
        staticmethod(lambda payload, status: stub),
    )

    response = test_client(url="/admin/domains_status/Failed", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_find_storages_by_domain_status(monkeypatch, test_client):
    """PUT /admin/domains/status/{status}/find_storages — webapp
    admin desktops-status page uses it to enqueue ``find`` tasks for
    every storage owned by desktops in a given status. Mirrors v3
    ``api_v3_admin_domains_find_storages`` (``@is_admin_or_manager``).
    """
    jwt = MockJWT()
    captured = {}

    def fake_find(payload, status):
        captured["status"] = status
        captured["role_id"] = payload["role_id"]
        return {"tasks_created": 7}

    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.find_storages_by_domain_status",
        staticmethod(fake_find),
    )

    response = test_client(
        url="/admin/domains/status/Failed/find_storages",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"tasks_created": 7}
    assert captured == {"status": "Failed", "role_id": "admin"}


def test_admin_virt_install_xml_sections_get(monkeypatch, test_client):
    """GET /admin/virt_install/xml_sections/{virt_id} — admin XML
    sections editor "Resources → virt_install → Edit XML" button.
    Mirrors v3 handler from commit 0d15e5511. The service returns
    ``{sections, xml_full}``; the test stubs the service so we pin
    the wire contract without touching the mock DB."""
    jwt = MockJWT()
    captured = {}

    def fake_get(virt_id):
        captured["virt_id"] = virt_id
        return {
            "sections": [{"key": "memory", "xml": "<memory>2048</memory>"}],
            "xml_full": "<domain>...</domain>",
        }

    monkeypatch.setattr(
        "api.services.xml_sections.get_virt_install_xml_sections",
        fake_get,
    )

    response = test_client(
        url="/admin/virt_install/xml_sections/vi-1",
        jwt=jwt,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["xml_full"] == "<domain>...</domain>"
    assert body["sections"][0]["key"] == "memory"
    assert captured == {"virt_id": "vi-1"}


def test_admin_virt_install_xml_sections_save(monkeypatch, test_client):
    """POST /admin/virt_install/xml_sections/{virt_id} — merges the
    edited sections back into the virt_install template's XML."""
    jwt = MockJWT()
    captured = {}

    def fake_save(virt_id, sections):
        captured["virt_id"] = virt_id
        captured["section_count"] = len(sections)
        return {"xml": "<merged/>", "valid": True}

    monkeypatch.setattr(
        "api.services.xml_sections.save_virt_install_xml_sections",
        fake_save,
    )

    response = test_client(
        url="/admin/virt_install/xml_sections/vi-1",
        method="POST",
        body={"sections": [{"key": "memory", "xml": "<memory>4096</memory>"}]},
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert captured == {"virt_id": "vi-1", "section_count": 1}


def test_admin_domains_save_as_virt_install(monkeypatch, test_client):
    """POST /admin/domains/xml_sections/{id}/save_virt_install —
    webapp "Save as virt_install" button in the XML sections editor."""
    jwt = MockJWT()
    captured = {}

    def fake_save(domain_id, edited_sections, name):
        captured["domain_id"] = domain_id
        captured["name"] = name
        captured["section_count"] = len(edited_sections)
        return {"id": "new_vi", "name": name}

    monkeypatch.setattr(
        "api.services.xml_sections.save_as_virt_install",
        fake_save,
    )

    response = test_client(
        url="/admin/domains/xml_sections/desktop-1/save_virt_install",
        method="POST",
        body={
            "sections": [{"key": "memory", "xml": "<memory>2048</memory>"}],
            "name": "My new VI template",
        },
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "new_vi", "name": "My new VI template"}
    assert captured == {
        "domain_id": "desktop-1",
        "name": "My new VI template",
        "section_count": 1,
    }


# ─── Async log-deletion BackgroundTasks remediation ─────────────────────


def _stub_log_delete_dependencies(monkeypatch):
    """Common monkeypatches for the log-delete BackgroundTasks tests.

    Returns a dict capturing what the inner task processed so each test
    can assert on it.
    """
    captured = {"deleted": [], "notifications": []}

    def fake_get_old(*args):
        # Mirrors ApiAdmin.get_older_than_old_entry_max_time(table[, max])
        return [{"id": f"log-{args[0]}-1"}, {"id": f"log-{args[0]}-2"}]

    def fake_delete_batch(table, rows):
        captured["deleted"].append((table, [r["id"] for r in rows]))

    def fake_notify(event, payload):
        captured["notifications"].append((event, payload))

    monkeypatch.setattr(
        "api.services.admin.domains.ApiAdmin.get_older_than_old_entry_max_time",
        staticmethod(fake_get_old),
    )
    monkeypatch.setattr(
        "api.services.admin.domains.LogsProcessed.delete_batch",
        staticmethod(fake_delete_batch),
    )
    monkeypatch.setattr(
        "api.services.admin.domains.notify_admins",
        fake_notify,
    )
    return captured


def test_admin_logs_desktops_delete_runs_batch_after_response(monkeypatch, test_client):
    """Pins the SIGSEGV remediation for ``services/admin/domains.py:419``.

    Previously this fired ``gevent.spawn(delete_old_logs_process)`` from
    an ``async def`` route — the spawned greenlet was queued on a libev
    Hub the asyncio worker never drives, so log deletion silently never
    ran. The fix routes the work through ``BackgroundTasks``; FastAPI's
    test client runs the task after the response is flushed, so
    ``LogsProcessed.delete_batch`` MUST have been called by the time
    ``response = test_client(...)`` returns.
    """
    jwt = MockJWT()
    captured = _stub_log_delete_dependencies(monkeypatch)

    response = test_client(
        url="/logs_desktops/old_entries/delete",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    assert response.json() == 2
    # Background task must have run before the TestClient returned.
    assert captured["deleted"] == [
        ("logs_desktops", ["log-logs_desktops-1", "log-logs_desktops-2"])
    ]
    assert captured["notifications"] == [
        ("logs_desktops_action", {"action": "delete_all", "status": "completed"})
    ]


def test_admin_logs_desktops_delete_all_runs_batch_after_response(
    monkeypatch, test_client
):
    """Same pattern as ``test_admin_logs_desktops_delete_runs_batch_after_response``
    but for the ``delete/all`` (max_time_arg=0) path.
    """
    jwt = MockJWT()
    captured = _stub_log_delete_dependencies(monkeypatch)

    response = test_client(
        url="/logs_desktops/old_entries/delete/all",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    assert captured["deleted"] == [
        ("logs_desktops", ["log-logs_desktops-1", "log-logs_desktops-2"])
    ]


def test_admin_logs_users_delete_runs_batch_after_response(monkeypatch, test_client):
    """Same pattern, for the user-logs delete route."""
    jwt = MockJWT()
    captured = _stub_log_delete_dependencies(monkeypatch)

    response = test_client(
        url="/logs_users/old_entries/delete",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    assert captured["deleted"] == [
        ("logs_users", ["log-logs_users-1", "log-logs_users-2"])
    ]
    assert captured["notifications"] == [
        ("logs_users_action", {"action": "delete_all", "status": "completed"})
    ]


def test_admin_logs_users_delete_all_runs_batch_after_response(
    monkeypatch, test_client
):
    """Same pattern, for the user-logs delete-all route."""
    jwt = MockJWT()
    captured = _stub_log_delete_dependencies(monkeypatch)

    response = test_client(
        url="/logs_users/old_entries/delete/all",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    assert captured["deleted"] == [
        ("logs_users", ["log-logs_users-1", "log-logs_users-2"])
    ]


def test_admin_multiple_actions_runs_bulk_action_after_response(
    monkeypatch, test_client
):
    """Pins the SIGSEGV remediation for ``_common/lib/api_admin.py:1138``.

    Previously ``ApiAdmin.multiple_actions`` fired
    ``gevent.spawn(process_bulk_action)``; under apiv4's asyncio worker
    the spawned greenlet never ran, so the bulk action silently no-op'd.
    The fix removes the gevent.spawn from ``_common`` (now synchronous)
    and the apiv4 service schedules the call via ``BackgroundTasks``.
    The inner ``DesktopEvents.desktops_toggle`` MUST have been called by
    the time the TestClient returns.
    """
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.owns_domain_id",
        staticmethod(lambda payload, domain_id: True),
    )
    toggle_args = []
    monkeypatch.setattr(
        "isardvdi_common.lib.api_admin.DesktopEvents.desktops_toggle",
        staticmethod(lambda ids, force=False: toggle_args.append((tuple(ids), force))),
    )

    response = test_client(
        url="/admin/multiple_actions",
        method="POST",
        body={"action": "toggle", "ids": ["d-1", "d-2"]},
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    # toggle with force=True (action == "toggle") MUST have run by now.
    assert toggle_args == [(("d-1", "d-2"), True)]


# ─── Logs DataTables routes — manager scoping (LG3 fix) ─────────────────


def test_admin_logs_desktops_allows_manager_with_category_scope(
    monkeypatch, test_client
):
    """Apiv3 ``@is_admin_or_manager`` parity: managers must reach
    ``POST /admin/logs_desktops`` and see only their category's rows.
    Pre-fix the route was on ``@admin_router`` so managers got 403."""
    jwt = MockJWT(role_id="manager", category_id="cat-manager")
    captured = {}

    def fake_query(form_data, view="raw", payload=None):
        captured["view"] = view
        captured["payload_role"] = payload.get("role_id") if payload else None
        captured["payload_category"] = payload.get("category_id") if payload else None
        return {"draw": 1, "recordsTotal": 0, "recordsFiltered": 0, "data": []}

    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.query_logs_desktops",
        staticmethod(fake_query),
    )

    response = test_client(
        url="/admin/logs_desktops",
        method="POST",
        body={"draw": 1, "start": 0, "length": 25, "columns": []},
        jwt=jwt,
        db_tables_data={"categories": [{"id": "cat-manager", "maintenance": False}]},
    )

    assert response.status_code == 200, response.text
    assert captured["view"] == "raw"
    assert captured["payload_role"] == "manager"
    assert captured["payload_category"] == "cat-manager"


def test_admin_logs_users_allows_manager_with_category_scope(monkeypatch, test_client):
    """Same parity check for the user-logs DataTables route."""
    jwt = MockJWT(role_id="manager", category_id="cat-manager")
    captured = {}

    def fake_query(form_data, view="raw", payload=None):
        captured["view"] = view
        captured["payload_role"] = payload.get("role_id") if payload else None
        return {"draw": 1, "recordsTotal": 0, "recordsFiltered": 0, "data": []}

    monkeypatch.setattr(
        "api.services.admin.domains.AdminDomainsService.query_logs_users",
        staticmethod(fake_query),
    )

    response = test_client(
        url="/admin/logs_users",
        method="POST",
        body={"draw": 1, "start": 0, "length": 25, "columns": []},
        jwt=jwt,
        db_tables_data={"categories": [{"id": "cat-manager", "maintenance": False}]},
    )

    assert response.status_code == 200, response.text
    assert captured["payload_role"] == "manager"
