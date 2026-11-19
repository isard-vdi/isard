# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``nextcloud.Helpers.start_login_auth``, which raised NameError on every call."""

import contextlib
import json
from unittest.mock import MagicMock

import pytest
from isardvdi_common.connections.user_storage_providers.nextcloud import Helpers

PROVIDER = {
    "url": "storage.example.org",
    "urlprefix": "/nc",
    "verify_cert": True,
}


@pytest.fixture
def provider_row(monkeypatch):
    """Serve ``PROVIDER`` for the ``user_storage`` read and stub the HTTP call."""
    monkeypatch.setattr(
        Helpers, "_rdb_context", classmethod(lambda cls: contextlib.nullcontext())
    )
    # a property of the pool metaclass, so it has to be patched there
    monkeypatch.setattr(type(Helpers), "_rdb_connection", MagicMock())

    import isardvdi_common.connections.user_storage_providers.nextcloud as nextcloud

    table = MagicMock()
    table.get.return_value.run.return_value = PROVIDER
    monkeypatch.setattr(nextcloud.r, "table", MagicMock(return_value=table))

    request = MagicMock(return_value=json.dumps({"login": "https://login.example.org"}))
    monkeypatch.setattr(
        Helpers, "_request", classmethod(lambda cls, *a, **k: request())
    )
    return request


def test_start_login_auth_returns_the_login_url(provider_row):
    """The happy path must reach the provider and hand back its login URL."""
    assert Helpers.start_login_auth("a-provider") == "https://login.example.org"
    assert provider_row.call_count == 1


def test_start_login_auth_does_not_read_an_undefined_global(provider_row):
    """A reintroduced undefined ``global`` is reported as a NameError by name."""
    try:
        Helpers.start_login_auth("a-provider")
    except NameError as exc:  # pragma: no cover - the regression this guards
        pytest.fail(f"start_login_auth raised NameError: {exc}")


def test_module_defines_no_login_thread_global():
    """No module-level ``login_thread``: the caller owns the watcher thread."""
    import isardvdi_common.connections.user_storage_providers.nextcloud as nextcloud

    assert not hasattr(nextcloud, "login_thread")
    assert not hasattr(Helpers, "login_thread")
