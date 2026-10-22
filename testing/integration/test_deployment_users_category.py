# SPDX-License-Identifier: AGPL-3.0-or-later

"""A manager's deployment never reaches the users of another category."""

from __future__ import annotations

import os
import time

import pytest
from isardvdi_apiv4_client.api.role_advanced import (
    create_deployment,
    delete_deployment,
    get_deployment,
)
from isardvdi_apiv4_client.api.role_user import get_user_allowed_templates_flat
from isardvdi_apiv4_client.models.allowed_base import AllowedBase
from isardvdi_apiv4_client.models.create_deployment_request import (
    CreateDeploymentRequest,
)
from isardvdi_apiv4_client.models.create_desktop_request import CreateDesktopRequest
from isardvdi_apiv4_client.models.deployment_response import DeploymentResponse
from isardvdi_apiv4_client.models.get_user_allowed_templates_flat_kind import (
    GetUserAllowedTemplatesFlatKind,
)

from .helpers.client import IsardClient
from .helpers.responses import created_id, expect
from .helpers.seed import derivable

MANAGER_USERNAME = os.environ.get("E2E_MANAGER01_USERNAME", "manager01")
MANAGER_PASSWORD = os.environ.get("E2E_MANAGER01_PASSWORD", "LB`*F9Uw")
MANAGER_CATEGORY = os.environ.get("E2E_MANAGER01_CATEGORY", "default")

# Seeded group of the "hidden" category: user02 and manager02.
FOREIGN_GROUP = "cca27c62-9db4-45a2-8faa-3897f095d507"
FOREIGN_USERS = {
    "f04ec876-a836-45fc-8014-3677386739a4",
    "161cb3cd-54b1-4937-a922-df57b1b8c483",
}
SETTLE_TIMEOUT = int(os.environ.get("E2E_CREATE_TIMEOUT", "180"))


@pytest.mark.real
def test_manager_deployment_skips_users_of_another_category(test_namespace: str):
    manager = IsardClient()
    manager.login(MANAGER_USERNAME, MANAGER_PASSWORD, category_id=MANAGER_CATEGORY)

    templates = expect(
        get_user_allowed_templates_flat.sync_detailed(
            kind=GetUserAllowedTemplatesFlatKind.ALL, client=manager.apiv4()
        )
    )
    templates = derivable(templates)
    if not templates:
        pytest.skip("no seeded template the manager can derive from")

    name = f"{test_namespace}foreign_group_dep"
    resp = create_deployment.sync_detailed(
        client=manager.apiv4(),
        body=CreateDeploymentRequest(
            name=name,
            description="category isolation",
            allowed=AllowedBase(users=[manager.user_id], groups=[FOREIGN_GROUP]),
            create_owner_desktop=False,
            visible=False,
            desktops=[
                CreateDesktopRequest(
                    template_id=templates[0].id, name=name, description=""
                )
            ],
        ),
    )
    if resp.status_code in (400, 403):
        return
    deployment_id = created_id(resp)

    try:
        with_desktop: set[str] = set()
        deadline = time.monotonic() + SETTLE_TIMEOUT
        while time.monotonic() < deadline:
            detail = expect(
                get_deployment.sync_detailed(
                    deployment_id=deployment_id, client=manager.apiv4()
                )
            )
            assert isinstance(detail, DeploymentResponse)
            with_desktop = {
                u.id
                for u in detail.users
                if sum(s.amount for s in u.desktops_statuses or []) > 0
            }
            if manager.user_id in with_desktop:
                break
            time.sleep(2.0)

        assert (
            manager.user_id in with_desktop
        ), "the manager's own desktop never appeared"
        leaked = with_desktop & FOREIGN_USERS
        assert not leaked, f"desktops created for users of another category: {leaked}"
    finally:
        delete_deployment.sync_detailed(
            deployment_id=deployment_id, client=manager.apiv4()
        )
