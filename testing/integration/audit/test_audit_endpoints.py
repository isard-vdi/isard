# SPDX-License-Identifier: AGPL-3.0-or-later

"""Probe every in-scope apiv4 endpoint with a realistic payload.

This isn't a normal pytest assertion suite — every request is recorded
into the session-scoped ``audit_results`` store regardless of outcome,
and the session teardown emits ``audit_report.md`` + ``audit_report.csv``.

The pytest assertion only fires for **5xx** responses; 4xx and 2xx are
recorded as informational. ``-m audit`` selects this suite; the default
pytest invocation skips it.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest

from testing.integration.audit.conftest import ScratchEntities
from testing.integration.audit.error_classifier import ErrorSignature, classify
from testing.integration.audit.frontend_overrides import get_override
from testing.integration.audit.payload_factory import gen_sample
from testing.integration.audit.report import Result
from testing.integration.audit.route_filter import included_routes
from testing.integration.helpers.client import IsardClient


def pytest_generate_tests(metafunc):
    """Parametrize ``test_endpoint`` over every in-scope route.

    OpenAPI fetch happens at collection time via a tiny standalone
    client; we can't use the ``openapi_spec`` fixture here because
    parametrization runs before fixtures resolve.
    """
    if "route" not in metafunc.fixturenames:
        return

    import os

    base = os.environ.get("APIV4_URL", "http://isard-apiv4:5000").rstrip("/")
    auth_url = os.environ.get("AUTH_URL", "http://isard-authentication:1313").rstrip(
        "/"
    )
    user = os.environ.get("E2E_ADMIN_USER", "admin_e2e_01")
    pwd = os.environ.get("E2E_ADMIN_PWD", "IsardTest1!")
    cat = os.environ.get("E2E_ADMIN_CATEGORY", "default")

    client = IsardClient(apiv4_url=base, auth_url=auth_url)
    try:
        client.login(user, pwd, category_id=cat)
    except Exception as exc:
        metafunc.parametrize(
            "route",
            [pytest.param(None, marks=pytest.mark.skip(reason=f"login failed: {exc}"))],
        )
        return

    resp = client._session.get(f"{base}/api/v4/openapi.json", timeout=15)
    if resp.status_code != 200:
        metafunc.parametrize(
            "route",
            [
                pytest.param(
                    None, marks=pytest.mark.skip(reason="openapi.json unreachable")
                )
            ],
        )
        return
    spec = resp.json()

    routes = included_routes(spec)
    metafunc.parametrize(
        "route",
        routes,
        ids=[f"{m} {p}" for m, p, _ in routes],
    )


def _resolve_path(path: str, scratch: ScratchEntities) -> str:
    """Replace ``{name}`` placeholders with scratch ids / sensible strings."""
    params = scratch.as_path_params()

    def sub(match: re.Match) -> str:
        name = match.group(1)
        return str(params.get(name, "x"))

    return re.sub(r"{([^}]+)}", sub, path)


def _build_payload(
    method: str, path: str, op: dict, spec: dict, scratch: ScratchEntities
) -> tuple[Any, str]:
    """Return ``(payload, source)`` where source is ``override`` or ``openapi``."""
    if method in {"GET", "DELETE"}:
        # Most GETs / DELETEs don't take a body; if they do (e.g. bulk
        # delete) the override registers it.
        override = get_override(method, path)
        if override:
            return override(scratch), "override"
        return None, "none"

    override = get_override(method, path)
    if override:
        return override(scratch), "override"

    body = op.get("requestBody") or {}
    content = body.get("content") or {}
    json_schema = (content.get("application/json") or {}).get("schema")
    if not json_schema:
        return None, "none"
    return gen_sample(json_schema, spec, namespace=scratch.namespace), "openapi"


# Inter-request throttle. Without it the apiv4 grpc backbone (used
# for session validation) trips on ENHANCE_YOUR_CALM after ~50 quick
# requests and the rest of the audit times out. 50 ms is enough to
# keep the keepalive pings within the throttle envelope.
_AUDIT_THROTTLE_S = float(os.environ.get("AUDIT_THROTTLE_S", "0.05"))


@pytest.mark.audit
def test_endpoint(
    route,
    admin_client: IsardClient,
    scratch_entities: ScratchEntities,
    openapi_spec: dict,
    audit_results: list[Result],
):
    if route is None:
        pytest.skip("no routes parametrized")
    method, path, op = route

    payload, source = _build_payload(method, path, op, openapi_spec, scratch_entities)
    resolved = _resolve_path(path, scratch_entities)

    kwargs: dict = {}
    if payload is not None:
        kwargs["json"] = payload

    if _AUDIT_THROTTLE_S > 0:
        import time as _time

        _time.sleep(_AUDIT_THROTTLE_S)
    resp = admin_client.raw(method, resolved, **kwargs)

    body_excerpt = ""
    sig: ErrorSignature | None = None
    if resp.status_code >= 400:
        try:
            body_excerpt = resp.text[:500]
        except Exception:
            body_excerpt = "(no body)"
        sig = classify(resp.status_code, resp.text)

    audit_results.append(
        Result(
            method=method,
            path=path,
            status=resp.status_code,
            signature=sig,
            body_excerpt=body_excerpt,
            payload_source=source,
        )
    )

    if resp.status_code >= 500:
        pytest.fail(
            f"5xx on {method} {resolved}: {sig.short() if sig else resp.text[:200]}"
        )
