# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the haproxy-sync (a.k.a. ``haproxy_bastion``) gRPC client
provider hook in ``isardvdi_common.helpers.bastion``.

Companion to ``connections/tests/test_api_sessions_provider.py``: same
dependency-injection pattern, same incident driver. ``models.targets``
shares the hook (``targets`` imports the private getter from
``bastion``) so registering the provider on the ``bastion`` module
must implicitly satisfy the ``targets`` module too — there is one
source of truth for the haproxy-sync channel across the monorepo.

Tests:

1. Calling ``_haproxy_bastion_client()`` before configuration raises a
   clear RuntimeError that names the configure function.
2. After ``configure_haproxy_bastion_client(provider)``, the same
   provider is observable through ``models.targets``' getter import,
   confirming there is no duplicate state.
3. Provider is invoked on every call (no caching at registration).
"""

import isardvdi_common.helpers.bastion as bastion_module
import pytest


@pytest.fixture(autouse=True)
def _reset_provider():
    """Each test starts with no provider registered."""
    yield
    bastion_module._haproxy_bastion_client_provider = None


def test_getter_without_configure_raises_clear_runtime_error():
    """Pre-configuration calls must raise a clear RuntimeError naming
    the configure function. apiv4's lifespan registers the provider
    before any request is served, but a developer running an
    individual unit test against ``Bastion.update_bastion_haproxy_map``
    needs an obvious error message, not an ``AttributeError`` on a
    None object.
    """
    with pytest.raises(RuntimeError) as excinfo:
        bastion_module._haproxy_bastion_client()
    msg = str(excinfo.value)
    assert "configure_haproxy_bastion_client" in msg
    assert "isardvdi_common.helpers.bastion" in msg


def test_configure_then_get_invokes_provider_lazily():
    """The provider closure is called on every invocation, not at
    registration. This lets apiv4 swap the underlying stub on a
    reconnect without re-running configure.
    """
    sentinel = object()
    invocations = []

    def provider():
        invocations.append(None)
        return sentinel

    bastion_module.configure_haproxy_bastion_client(provider)

    # Each call hits the provider exactly once — registration alone
    # does NOT invoke the provider.
    assert invocations == []
    assert bastion_module._haproxy_bastion_client() is sentinel
    assert bastion_module._haproxy_bastion_client() is sentinel
    assert bastion_module._haproxy_bastion_client() is sentinel
    assert len(invocations) == 3


def test_targets_module_shares_the_same_hook():
    """``isardvdi_common.models.targets`` imports the private getter
    from this module so a single provider registration is honoured by
    both. Verify by registering one provider and observing the same
    function object reference from both modules — guards against a
    future refactor accidentally duplicating provider state (which
    would silently let the two modules drift apart, causing
    subdomain operations from one path to use a stale stub).
    """
    import isardvdi_common.models.targets as targets_module

    # The two modules must reference the same getter function — that's
    # the only way a registration on `bastion` is observable from
    # `targets`.
    assert (
        targets_module._haproxy_bastion_client is bastion_module._haproxy_bastion_client
    ), (
        "models.targets must import the same _haproxy_bastion_client "
        "function as helpers.bastion. If this fails, the targets "
        "module has its own provider state and will silently use the "
        "wrong (or no) gRPC stub."
    )

    sentinel = object()
    bastion_module.configure_haproxy_bastion_client(lambda: sentinel)

    # Calling either module's getter returns the same sentinel,
    # proving the provider state is shared.
    assert bastion_module._haproxy_bastion_client() is sentinel
    assert targets_module._haproxy_bastion_client() is sentinel
