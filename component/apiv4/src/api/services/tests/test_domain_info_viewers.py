# SPDX-License-Identifier: AGPL-3.0-or-later

"""RDP viewers only work through the wireguard network, so ``get-info`` drops
them when the domain has no wireguard interface. They are reported apart from
``limited_hardware``: viewers are not hardware and the cause is the missing
network, not the user hardware permissions.
"""

import copy

DOMAIN_DEF = {
    "id": "desktop-1",
    "kind": "desktop",
    "name": "Desktop 1",
    "guest_properties": {
        "viewers": {
            "file_spice": {"options": None},
            "browser_rdp": {"options": None},
            "file_rdpgw": {"options": None},
        }
    },
}


def make_service(monkeypatch, interfaces):
    from api.services import domains as svc

    monkeypatch.setattr(
        svc.Caches,
        "get_document",
        staticmethod(lambda *a, **kw: copy.deepcopy(DOMAIN_DEF)),
    )
    monkeypatch.setattr(
        svc.CommonDomains,
        "get_domain_hardware",
        classmethod(
            lambda cls, *a, **kw: {
                "hardware": {
                    "interfaces": [{"id": iface, "mac": None} for iface in interfaces]
                }
            }
        ),
    )
    monkeypatch.setattr(
        svc.Quotas,
        "limit_user_hardware_allowed",
        classmethod(lambda cls, payload, domain: domain),
    )
    monkeypatch.setattr(
        svc.Interface,
        "get_interfaces_names",
        staticmethod(lambda *a, **kw: {}),
    )
    return svc.DomainService


def test_rdp_viewers_are_dropped_without_wireguard(monkeypatch):
    service = make_service(monkeypatch, ["default"])

    domain = service.get_domain_info("desktop-1", {"role_id": "user"})

    assert domain["removed_viewers"] == ["browser_rdp", "file_rdpgw"]
    assert domain["guest_properties"]["viewers"] == {"file_spice": {"options": None}}
    assert domain.get("limited_hardware") is None


def test_rdp_viewers_are_kept_with_wireguard(monkeypatch):
    service = make_service(monkeypatch, ["default", "wireguard"])

    domain = service.get_domain_info("desktop-1", {"role_id": "user"})

    assert "removed_viewers" not in domain
    assert set(domain["guest_properties"]["viewers"]) == {
        "file_spice",
        "browser_rdp",
        "file_rdpgw",
    }
