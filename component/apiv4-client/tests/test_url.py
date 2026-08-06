"""Contract tests for base URL resolution."""

import pytest
from isardvdi_apiv4_client_auth._url import resolve_base_url


def test_defaults_to_cluster_dns_http(monkeypatch):
    monkeypatch.delenv("API_DOMAIN", raising=False)
    url, verify = resolve_base_url()
    assert url == "http://isard-apiv4:5000"
    assert verify is False


def test_respects_api_domain_override_hostname(monkeypatch):
    monkeypatch.setenv("API_DOMAIN", "isardvdi.example.com")
    url, verify = resolve_base_url()
    assert url == "https://isardvdi.example.com"
    assert verify is True


def test_respects_api_domain_override_ip(monkeypatch):
    monkeypatch.setenv("API_DOMAIN", "10.0.0.5")
    url, verify = resolve_base_url()
    assert url == "https://10.0.0.5"
    assert verify is False


def test_respects_api_domain_override_localhost(monkeypatch):
    monkeypatch.setenv("API_DOMAIN", "localhost")
    url, verify = resolve_base_url()
    assert url == "http://localhost:5000"
    assert verify is False


def test_api_domain_value_isard_api_treated_as_default(monkeypatch):
    """Backwards-compat with the legacy setting — some envs still set
    ``API_DOMAIN=isard-api``. Treat it the same as empty.
    """
    monkeypatch.setenv("API_DOMAIN", "isard-api")
    url, verify = resolve_base_url()
    assert url == "http://isard-apiv4:5000"
