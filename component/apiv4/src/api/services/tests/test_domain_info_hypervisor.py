# SPDX-License-Identifier: AGPL-3.0-or-later

"""``get-info`` feeds the detail panel of every role, so the hypervisor a
domain runs on is only filled in for admins — it is the one field of the
payload that describes the infrastructure and not the domain itself.
"""

import pytest

DOMAIN_DEF = {
    "id": "desktop-1",
    "kind": "desktop",
    "name": "Desktop 1",
    "status": "Started",
    "hyp_started": "hyp-a",
}


@pytest.fixture
def service(monkeypatch):
    from api.services import domains as svc

    monkeypatch.setattr(
        svc.Caches,
        "get_document",
        staticmethod(lambda *a, **kw: dict(DOMAIN_DEF)),
    )
    monkeypatch.setattr(
        svc.CommonDomains,
        "get_domain_hardware",
        classmethod(lambda cls, *a, **kw: {"hardware": {}}),
    )
    monkeypatch.setattr(
        svc.Quotas,
        "limit_user_hardware_allowed",
        classmethod(lambda cls, payload, domain: domain),
    )
    yield svc.DomainService


@pytest.mark.parametrize("role", ["user", "advanced", "manager"])
def test_hypervisor_is_hidden_from_non_admins(service, role):
    domain = service.get_domain_info("desktop-1", {"role_id": role})

    assert domain["hyp_started"] is None


def test_admins_still_get_the_hypervisor(service):
    domain = service.get_domain_info("desktop-1", {"role_id": "admin"})

    assert domain["hyp_started"] == "hyp-a"
