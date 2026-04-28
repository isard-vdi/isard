"""Contract tests for isardvdi_apiv4_client_auth._jwt.

The minted JWT has to be byte-for-byte compatible with the service
tokens the legacy hand-written REST wrappers produced, because apiv4
verifies the ``kid`` + secret before anything else.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from isardvdi_apiv4_client_auth._jwt import mint_service_token


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("API_ISARDVDI_SECRET", "admin-secret")
    monkeypatch.setenv("API_HYPERVISORS_SECRET", "hypervisor-secret")


def test_admin_token_decodes_with_admin_secret():
    token = mint_service_token("isard-scheduler", role="admin")
    decoded = jwt.decode(token, "admin-secret", algorithms=["HS256"])
    assert decoded["kid"] == "isardvdi"
    assert decoded["session_id"] == "isardvdi-service"
    assert decoded["data"]["role_id"] == "admin"
    assert decoded["data"]["user_id"] == "isard-scheduler"
    assert decoded["data"]["category_id"] == "*"


def test_hypervisor_token_decodes_with_hypervisor_secret():
    token = mint_service_token("isard-hypervisor", role="hypervisor")
    decoded = jwt.decode(token, "hypervisor-secret", algorithms=["HS256"])
    assert decoded["kid"] == "isardvdi-hypervisors"
    assert decoded["data"]["role_id"] == "hypervisor"
    assert decoded["data"]["category_id"] == "default"


def test_token_is_short_lived():
    token = mint_service_token("isard-scheduler", role="admin")
    decoded = jwt.decode(token, "admin-secret", algorithms=["HS256"])
    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    # 20s default; allow a tiny skew
    assert timedelta(seconds=15) < (exp - now) <= timedelta(seconds=25)


def test_admin_role_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("API_ISARDVDI_SECRET", raising=False)
    with pytest.raises(KeyError, match="API_ISARDVDI_SECRET"):
        mint_service_token("isard-scheduler", role="admin")


def test_hypervisor_role_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("API_HYPERVISORS_SECRET", raising=False)
    with pytest.raises(KeyError, match="API_HYPERVISORS_SECRET"):
        mint_service_token("isard-hypervisor", role="hypervisor")


def test_unknown_role_raises():
    with pytest.raises(ValueError, match="role"):
        mint_service_token("isard-scheduler", role="user")  # type: ignore[arg-type]
