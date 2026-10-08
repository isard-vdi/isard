#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin hypervisor list with records the engine could not fully refresh."""

import pytest
from tests.routes.helpers import MockJWT


def _hypervisor(hyper_id, **extra):
    doc = {
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
        "status": "Online",
        "enabled": True,
    }
    doc.update(extra)
    return doc


def _serve(monkeypatch, rows):
    monkeypatch.setattr(
        "api.services.admin.hypervisors.AdminHypervisorsService.get_hypervisors",
        staticmethod(lambda status=None: rows),
    )


@pytest.mark.parametrize(
    "url", ["/admin/items/hypervisors", "/admin/items/hypervisors/Online"]
)
def test_mountpoints_false_does_not_break_the_list(monkeypatch, test_client, url):
    _serve(
        monkeypatch,
        [
            _hypervisor("hyper-ok", mountpoints=[{"mount": "/", "usage": 10}]),
            _hypervisor("hyper-stale", mountpoints=False),
        ],
    )

    response = test_client(url=url, jwt=MockJWT())

    assert response.status_code == 200
    body = {h["id"]: h for h in response.json()}
    assert set(body) == {"hyper-ok", "hyper-stale"}
    assert body["hyper-stale"]["mountpoints"] == []
    assert body["hyper-ok"]["mountpoints"] == [{"mount": "/", "usage": 10}]


def test_one_invalid_record_does_not_hide_the_others(monkeypatch, test_client):
    _serve(
        monkeypatch,
        [_hypervisor("hyper-ok"), _hypervisor("hyper-bad", status="NotAStatus")],
    )

    response = test_client(url="/admin/items/hypervisors", jwt=MockJWT())

    assert response.status_code == 200
    assert [h["id"] for h in response.json()] == ["hyper-ok"]
