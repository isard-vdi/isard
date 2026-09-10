import pytest

from webapp import inject_faro


def test_reports_every_request_by_default(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.delenv("FARO_HTTP_SAMPLING", raising=False)

    assert inject_faro()["faro_http_sampling"] == 1.0


def test_reads_the_sampling_rate_from_the_environment(monkeypatch):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("FARO_HTTP_SAMPLING", "0.5")

    assert inject_faro()["faro_http_sampling"] == 0.5


@pytest.mark.parametrize("value", ["7", "-1", "molt"])
def test_falls_back_when_the_rate_is_invalid(monkeypatch, value):
    monkeypatch.setenv("FARO_ENABLED", "true")
    monkeypatch.setenv("FARO_HTTP_SAMPLING", value)

    assert inject_faro()["faro_http_sampling"] == 1.0
