# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pytest fixtures for the audit suite.

Extends ``testing/integration/conftest.py`` (admin_client, test_namespace,
session cleanup hook) with:
- ``openapi_spec`` — fetched once per session from the live apiv4
- ``scratch_entities`` — one user/group/category/desktop/template/media
  prefixed ``e2e_audit_<worker>_<ts>_`` so cleanup_by_prefix can sweep
- ``audit_results`` — in-process result store flushed to Markdown + CSV
  at session teardown
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import pytest

from testing.integration.helpers.cleanup import cleanup_by_prefix
from testing.integration.helpers.client import IsardClient

from .report import Result, to_csv, to_markdown

log = logging.getLogger("audit.conftest")


@dataclass
class ScratchEntities:
    """IDs of audit-owned entities; consumed by path-param resolution."""

    namespace: str
    user_id: str = ""
    group_id: str = ""
    category_id: str = ""
    desktop_id: str = ""
    template_id: str = ""
    media_id: str = ""
    deployment_id: str = ""
    domain_id: str = ""

    def as_path_params(self) -> dict[str, str]:
        """Mapping for ``str.format(**this)``-style param substitution."""
        return {
            "user_id": self.user_id or "00000000-0000-0000-0000-000000000000",
            "group_id": self.group_id or "default-default",
            "category_id": self.category_id or "default",
            "desktop_id": self.desktop_id or "00000000-0000-0000-0000-000000000000",
            "template_id": self.template_id or "00000000-0000-0000-0000-000000000000",
            "media_id": self.media_id or "00000000-0000-0000-0000-000000000000",
            "deployment_id": self.deployment_id
            or "00000000-0000-0000-0000-000000000000",
            "domain_id": self.domain_id or "00000000-0000-0000-0000-000000000000",
            "id": self.user_id or "00000000-0000-0000-0000-000000000000",
            # registries take "domains" or "media"; never "category".
            # VPN endpoints take kind in {config, install} — those routes
            # are exercised in a smaller batch where {kind} == "config".
            "kind": "domains",
            "table": "users",
            "nav": "management",
            "action": "list",
            "status": "Stopped",
            "field": "name",
            "hyper_id": "isard-hypervisor",
            "user": "default",
            "target_user_id": "local-default-admin-admin",
            "current_status": "Stopped",
            "target_status": "Stopped",
            "kind_id": "default",
            "item_id": "default",
            "max_time": "30",
            "name": "default",
            "page": "1",
            "limit": "10",
            "ordered_by": "name",
            "secondary_group_id": "default-default",
            "policy_id": "default",
            "secret_id": "00000000-0000-0000-0000-000000000000",
            "key_id": "00000000-0000-0000-0000-000000000000",
            "kid": "00000000-0000-0000-0000-000000000000",
            "agent_id": "audit-agent",
            "old_status": "Stopped",
            "domain_kind": "desktop",
            "viewer_kind": "browser-vnc",
            "image_id": "stock-default",
            "deployment_action": "list",
            "auth_provider": "local",
            "auth_provider_id": "local",
            "user_provider": "local",
            "vpn_kind": "users",
            "os_kind": "Linux",
        }


@pytest.fixture(scope="session")
def openapi_spec(admin_client: IsardClient) -> dict:
    """Fetch /api/v4/openapi.json once per session."""
    resp = admin_client.raw("GET", "/api/v4/openapi.json")
    if resp.status_code != 200:
        pytest.skip(f"openapi.json not reachable: HTTP {resp.status_code}")
    return resp.json()


@pytest.fixture(scope="session")
def scratch_entities(
    admin_client: IsardClient, test_namespace: str
) -> Iterator[ScratchEntities]:
    """Create one of each entity the audit needs to exercise paths.

    All names use ``test_namespace`` as a prefix so the parent
    ``cleanup_by_prefix("e2e_real_")`` autouse fixture sweeps them at
    teardown without extra plumbing.
    """
    ns = test_namespace.rstrip("_")
    scratch = ScratchEntities(namespace=ns)

    # user
    try:
        user = admin_client.post(
            "/api/v4/admin/user",
            json_body={
                "name": f"{ns}_u",
                "email": "",
                "email-verified": "on",
                "role": "user",
                "category": "default",
                "group": "default-default",
                "password": "AuditPwd1!",
                "email_verified": True,
                "provider": "local",
                "bulk": False,
                "username": f"{ns}_u",
            },
        )
        scratch.user_id = user["id"]
    except Exception as exc:
        log.warning("scratch user create failed: %s", exc)

    # group
    try:
        grp = admin_client.post(
            "/api/v4/admin/group",
            json_body={
                "name": f"{ns}_g",
                "description": "audit",
                "parent_category": "default",
            },
        )
        scratch.group_id = grp["id"]
    except Exception as exc:
        log.warning("scratch group create failed: %s", exc)

    # category
    try:
        cat = admin_client.post(
            "/api/v4/admin/category",
            json_body={
                "name": f"{ns}_c",
                "description": "audit",
                "custom_url_name": f"{ns}_c",
                "recycle": {"bin": {"cutoff": {"time": "1"}}},
                "frontend": False,
                "maintenance": False,
                "recycle_bin_cutoff_time": None,
                "manager_permissions": {
                    "authentication": False,
                    "branding": False,
                    "login_notification": False,
                },
            },
        )
        scratch.category_id = cat["id"]
    except Exception as exc:
        log.warning("scratch category create failed: %s", exc)

    yield scratch
    # cleanup happens via the parent autouse hook (cleanup_by_prefix)


@pytest.fixture(scope="session")
def audit_results() -> Iterator[list[Result]]:
    """In-process collection of every probe result; flushed at session end."""
    results: list[Result] = []
    yield results

    out_dir = Path(__file__).parent
    if results:
        (out_dir / "audit_report.md").write_text(to_markdown(results))
        (out_dir / "audit_report.csv").write_text(to_csv(results))
        log.warning(
            "audit: wrote audit_report.md + audit_report.csv with %d results",
            len(results),
        )
