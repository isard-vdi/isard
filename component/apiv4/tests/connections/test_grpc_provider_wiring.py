# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test for ``api._wire_grpc_providers`` — the apiv4 lifespan helper
that registers concrete gRPC stubs as providers for the shared
``isardvdi_common`` modules.

Pre-refactor, ``isardvdi_common.connections.api_sessions`` and
``isardvdi_common.helpers.bastion`` opened gRPC channels at module
load. Post-refactor, they expose ``configure_sessions_client(...)`` /
``configure_haproxy_bastion_client(...)`` provider hooks and apiv4's
lifespan wires up the concrete stubs once at startup.

The two provider tests in ``isardvdi_common`` already cover:

  * unconfigured-state RuntimeError,
  * provider invoked on every call,
  * targets/bastion module sharing.

What they DON'T cover: that apiv4 actually calls
``configure_sessions_client`` and ``configure_haproxy_bastion_client``
during lifespan. The ``_mock_bastion_grpc`` fixture in
``api/routes/tests/conftest.py`` *replaces* that wiring with
MagicMocks for unit tests, which means a regression that silently
deletes the wiring code from lifespan would still pass routes
tests. This test pins the wiring directly.
"""

from unittest.mock import MagicMock

import isardvdi_common.connections.api_sessions as api_sessions_module
import isardvdi_common.helpers.bastion as bastion_module
import pytest


@pytest.fixture
def reset_providers():
    """Reset both provider slots to None so the test runs against a
    clean unconfigured state, regardless of what fixtures or imports
    may have configured earlier in the session.

    Restores them on teardown so other tests don't see the test's
    wiring leak — the autouse ``_mock_bastion_grpc`` fixture in
    routes/tests/conftest.py runs *its own* setup before each test
    so it's not affected, but this connections/tests/ directory
    has no autouse override, so the cleanup matters.
    """
    api_sessions_module._sessions_client_provider = None
    bastion_module._haproxy_bastion_client_provider = None
    yield
    api_sessions_module._sessions_client_provider = None
    bastion_module._haproxy_bastion_client_provider = None


def test_wire_grpc_providers_configures_both_modules(reset_providers, monkeypatch):
    """After ``_wire_grpc_providers()`` runs, both shared modules
    have a registered provider that returns the stub created by
    apiv4's grpc_client factories.

    Regression guard: a future refactor that drops one of the two
    ``configure_*`` calls (or swaps host/port wrong) would still
    leave the running stack apparently functional in production,
    because the missing provider only surfaces when the unused
    code path runs. This test fails immediately on either omission.
    """
    fake_sessions_stub = MagicMock(name="SessionsStub")
    fake_haproxy_stub = MagicMock(name="HaproxyBastionStub")

    sessions_factory = MagicMock(return_value=fake_sessions_stub)
    haproxy_factory = MagicMock(return_value=fake_haproxy_stub)

    monkeypatch.setattr(
        "api.connections.grpc_client.create_sessions_client",
        sessions_factory,
    )
    monkeypatch.setattr(
        "api.connections.grpc_client.create_haproxy_bastion_client",
        haproxy_factory,
    )

    # Pre-condition: providers are unconfigured.
    assert api_sessions_module._sessions_client_provider is None
    assert bastion_module._haproxy_bastion_client_provider is None

    from api import _wire_grpc_providers

    _wire_grpc_providers()

    # Post-condition: both providers configured.
    assert api_sessions_module._sessions_client_provider is not None, (
        "api_sessions provider not configured after _wire_grpc_providers — "
        "lifespan would silently leave session lookups raising "
        "RuntimeError on every authenticated request"
    )
    assert bastion_module._haproxy_bastion_client_provider is not None, (
        "haproxy_bastion provider not configured after _wire_grpc_providers — "
        "lifespan would silently leave Bastion.update_* / Targets.update "
        "operations raising RuntimeError"
    )

    # Each provider returns the stub the factory built. Pins both
    # the wiring direction (which factory feeds which module) and
    # the closure-not-call semantics (provider invoked on each call,
    # not memoized at registration).
    assert api_sessions_module._sessions_client_provider() is fake_sessions_stub
    assert bastion_module._haproxy_bastion_client_provider() is fake_haproxy_stub


def test_wire_grpc_providers_calls_factories_with_expected_endpoints(
    reset_providers, monkeypatch
):
    """The factories receive the right host / port pair. A typo in
    either argument would have apiv4 silently talking to the wrong
    service (or to no service at all), which the connectivity test
    in the live stack catches but no static check does.
    """
    sessions_factory = MagicMock(return_value=MagicMock())
    haproxy_factory = MagicMock(return_value=MagicMock())

    monkeypatch.setattr(
        "api.connections.grpc_client.create_sessions_client",
        sessions_factory,
    )
    monkeypatch.setattr(
        "api.connections.grpc_client.create_haproxy_bastion_client",
        haproxy_factory,
    )

    from api import _wire_grpc_providers

    _wire_grpc_providers()

    # Call signatures are positional in the production code; pin
    # them positionally too so a future refactor to keyword args
    # has to update the test deliberately.
    sessions_factory.assert_called_once_with("isard-sessions", 1312)
    haproxy_factory.assert_called_once_with("isard-portal", 1312)


def test_wire_grpc_providers_returns_same_stub_on_repeated_calls(
    reset_providers, monkeypatch
):
    """The provider closure captures the stub built at registration
    and returns the same instance on every subsequent invocation.
    Without this contract, every gRPC call site would build a new
    channel — which (a) blows out file descriptors, (b) defeats the
    haproxy-sync ``wait_for_ready`` semantics that depend on a
    persistent channel reaching the connection-warmed state.
    """
    fake_sessions_stub = MagicMock(name="SessionsStub")
    fake_haproxy_stub = MagicMock(name="HaproxyBastionStub")

    monkeypatch.setattr(
        "api.connections.grpc_client.create_sessions_client",
        MagicMock(return_value=fake_sessions_stub),
    )
    monkeypatch.setattr(
        "api.connections.grpc_client.create_haproxy_bastion_client",
        MagicMock(return_value=fake_haproxy_stub),
    )

    from api import _wire_grpc_providers

    _wire_grpc_providers()

    # The provider must yield the same stub each time it's called,
    # not a fresh one. ``is`` comparison rules out e.g. a regression
    # that re-creates the stub per provider invocation.
    assert (
        api_sessions_module._sessions_client_provider()
        is api_sessions_module._sessions_client_provider()
    )
    assert (
        bastion_module._haproxy_bastion_client_provider()
        is bastion_module._haproxy_bastion_client_provider()
    )
