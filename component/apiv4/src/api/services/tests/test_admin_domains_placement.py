# SPDX-License-Identifier: AGPL-3.0-or-later

"""Managers must not receive the hypervisor placement of the domains they
list. The webapp hides the ``hyp_started`` / ``forced_hyp`` columns for
them, but hiding a column does not stop the value from reaching the
browser: the fields are left out of the query instead, and the response
model fills them with null for the tables.
"""

import pytest

MANAGER = {"role_id": "manager", "category_id": "cat-1"}
ADMIN = {"role_id": "admin"}


@pytest.fixture
def service(monkeypatch):
    from api.services.admin import domains as svc

    calls = {}

    def _capture(name):
        def _fake(cls, *args, **kwargs):
            calls[name] = kwargs
            return []

        return classmethod(_fake)

    monkeypatch.setattr(svc.ApiAdmin, "list_desktops", _capture("desktops"))
    monkeypatch.setattr(
        svc.ApiAdmin, "list_desktops_with_filters", _capture("filtered")
    )
    monkeypatch.setattr(svc.ApiAdmin, "list_templates", _capture("templates"))
    yield svc.AdminDomainsService, calls


def test_manager_desktops_are_listed_without_placement(service):
    admin_domains, calls = service

    admin_domains.list_desktops(MANAGER)

    assert calls["filtered"]["placement"] is False


def test_manager_templates_are_listed_without_placement(service):
    admin_domains, calls = service

    admin_domains.list_templates(MANAGER)

    assert calls["templates"]["placement"] is False


def test_admin_desktops_keep_placement(service):
    admin_domains, calls = service

    admin_domains.list_desktops(ADMIN)

    assert calls["desktops"]["placement"] is True
