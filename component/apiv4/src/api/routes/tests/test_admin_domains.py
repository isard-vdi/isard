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
