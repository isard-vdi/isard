"""Contract tests for build_client()."""

import pytest
from isardvdi_apiv4_client_auth import build_client, raise_for_status
from isardvdi_apiv4_client_auth._errors import ApiV4Error


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("API_ISARDVDI_SECRET", "admin-secret")
    monkeypatch.setenv("API_HYPERVISORS_SECRET", "hypervisor-secret")
    monkeypatch.delenv("API_DOMAIN", raising=False)


def test_returns_authenticated_client_with_bearer_token():
    client = build_client("isard-scheduler")
    # openapi-python-client exposes the token via `.token` on AuthenticatedClient
    assert client.token.count(".") == 2  # JWT shape: three dot-separated segments
    # URL correctness already covered by tests/test_url.py; here just confirm wiring
    assert "isard-apiv4" in str(client._base_url)


def test_admin_role_default():
    """If ``role`` is omitted, admin is used."""
    admin_default = build_client("isard-notifier")
    admin_explicit = build_client("isard-notifier", role="admin")
    # Tokens differ (exp changes), but the claim shape should match.
    import jwt as pyjwt

    a = pyjwt.decode(admin_default.token, "admin-secret", algorithms=["HS256"])
    b = pyjwt.decode(admin_explicit.token, "admin-secret", algorithms=["HS256"])
    assert a["data"]["role_id"] == b["data"]["role_id"] == "admin"


def test_hypervisor_role_uses_hypervisors_secret():
    client = build_client("isard-hypervisor", role="hypervisor")
    import jwt as pyjwt

    decoded = pyjwt.decode(client.token, "hypervisor-secret", algorithms=["HS256"])
    assert decoded["kid"] == "isardvdi-hypervisors"


def test_user_jwt_passthrough_does_not_mint():
    client = build_client("isard-webapp", user_jwt="user-token-xyz")
    assert client.token == "user-token-xyz"


def test_clients_share_one_connection_pool():
    first = build_client("isard-scheduler")
    second = build_client("isard-scheduler")

    assert first.get_httpx_client()._transport is second.get_httpx_client()._transport


def test_leaving_the_context_manager_keeps_the_pool_alive():
    with build_client("isard-scheduler") as client:
        transport = client.get_httpx_client()._transport

    assert build_client("isard-scheduler").get_httpx_client()._transport is transport


def test_with_timeout_keeps_the_shared_pool():
    """docker/storage evolves the client; evolve must carry httpx_args."""
    import httpx

    client = build_client("isard-storage")
    evolved = client.with_timeout(httpx.Timeout(120.0))

    assert evolved.get_httpx_client()._transport is client.get_httpx_client()._transport


def test_raise_for_status_reexported():
    """Must be importable from the subpackage init for convenience."""
    assert callable(raise_for_status)
    assert ApiV4Error.__name__ == "ApiV4Error"
