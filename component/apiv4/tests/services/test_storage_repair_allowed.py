# SPDX-License-Identifier: AGPL-3.0-or-later

"""Only admins edit the costly-repair allowed list, and a start blocked by a disk handles it."""

import pytest
from api.services import desktops as desktops_module
from api.services.admin.alloweds import AdminAllowedsService
from api.services.desktops import DesktopService
from api.services.storage_problems import StorageProblemsService
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.helpers.error_factory import Error as CommonError

ALLOWED = {"roles": ["manager"], "categories": False, "groups": False, "users": False}


def test_an_admin_writes_the_list(monkeypatch):
    written = []
    monkeypatch.setattr(
        "api.services.admin.alloweds.Alloweds.update_storage_repair_alloweds",
        lambda allowed: written.append(allowed),
    )
    AdminAllowedsService.update_allowed(
        "storage_repair", {"id": "1", "allowed": ALLOWED}, {"role_id": "admin"}, None
    )
    assert written == [ALLOWED]


@pytest.mark.parametrize("role", ["manager", "advanced", "user"])
def test_nobody_but_an_admin_reads_or_writes_the_list(monkeypatch, role):
    written = []
    monkeypatch.setattr(
        "api.services.admin.alloweds.Alloweds.update_storage_repair_alloweds",
        lambda allowed: written.append(allowed),
    )
    payload = {"role_id": role, "user_id": "u1", "category_id": "c1"}
    with pytest.raises(ErrorBase) as raised:
        AdminAllowedsService.update_allowed(
            "storage_repair", {"id": "1", "allowed": ALLOWED}, payload, None
        )
    assert raised.value.status_code == 403
    with pytest.raises(ErrorBase):
        AdminAllowedsService.get_allowed_table("storage_repair", {"id": "1"}, payload)
    assert written == []


def test_the_list_is_read_with_its_names(monkeypatch):
    monkeypatch.setattr(
        "api.services.admin.alloweds.Alloweds.get_storage_repair_allowed_dict",
        lambda: ALLOWED,
    )
    monkeypatch.setattr(
        "api.services.admin.alloweds.Alloweds.get_allowed",
        lambda allowed: {"named": allowed},
    )
    out = AdminAllowedsService.get_allowed_table(
        "storage_repair", {"id": "1"}, {"role_id": "admin"}
    )
    assert out == {"named": ALLOWED}


@pytest.fixture
def start(monkeypatch):
    handled = []
    module = "api.services.desktops"
    monkeypatch.setattr(f"{module}.RethinkDomain.exists", lambda i: True)
    monkeypatch.setattr(
        f"{module}.CommonDesktops.clean_missing_reservables", lambda i: None
    )
    monkeypatch.setattr(
        f"{module}.Helpers.gen_payload_from_user",
        lambda user_id: {"user_id": user_id, "role_id": "user"},
    )
    monkeypatch.setattr(
        f"{module}.Helpers.owns_deployment_desktop_id", lambda **k: False
    )
    monkeypatch.setattr(f"{module}.Quotas.desktop_start", lambda u, d: {})
    monkeypatch.setattr(
        f"{module}.CommonDesktops._parse_desktop_booking",
        lambda d: {"needs_booking": False},
    )
    monkeypatch.setattr(
        StorageProblemsService,
        "handle_quietly",
        staticmethod(lambda payload, desktop_id: handled.append(desktop_id)),
    )
    return handled


def _refuse(code):
    def desktop_start(desktop_id):
        raise CommonError("precondition_required", "refused", description_code=code)

    return desktop_start


def test_a_start_blocked_by_its_disks_handles_them_and_keeps_the_error(
    monkeypatch, start
):
    monkeypatch.setattr(
        desktops_module.DesktopEvents,
        "desktop_start",
        staticmethod(_refuse("desktop_storage_not_ready")),
    )
    with pytest.raises(ErrorBase) as raised:
        DesktopService.start_desktop("d1", "u1")
    assert raised.value.error["description_code"] == "desktop_storage_not_ready"
    assert start == ["d1"]


def test_a_start_refused_for_another_reason_leaves_the_disks_alone(monkeypatch, start):
    monkeypatch.setattr(
        desktops_module.DesktopEvents,
        "desktop_start",
        staticmethod(_refuse("unable_to_start_desktop_from")),
    )
    with pytest.raises(ErrorBase):
        DesktopService.start_desktop("d1", "u1")
    assert start == []
