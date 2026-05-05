# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the sessions-client provider hook in
``isardvdi_common.connections.api_sessions``.

Background — incidents 2026-05-01 and 2026-05-05: the previous version
of this module created a sessions gRPC channel at module-load time and
the sibling ``grpc_client`` factory ran ``grpc.experimental.gevent.init_gevent()``
unconditionally. The combination loaded gevent's libev native extension
into apiv4's asyncio worker and SIGSEGV'd under concurrent load. The
factories now live in ``api.connections.grpc_client`` (apiv4-local) and
this module exposes a ``configure_sessions_client`` provider hook that
apiv4 wires up at lifespan startup.

These tests guard the contract:

1. Importing the module never opens a gRPC channel and never loads gevent.
2. Calling a session operation before ``configure_sessions_client`` is
   invoked raises a clear ``RuntimeError`` (not silent failure).
3. Once configured, every call invokes the registered provider — so
   apiv4 can replace the underlying stub at runtime if needed.
4. The public ``Error`` sentinels (``no_session``, ``expired_session``,
   ``invalid_session``, ``invalid_user``) are stable — existing callers
   in ``isardvdi_common.lib.users.users.user`` compare error identity
   (``e in [expired_session, invalid_user]``) and that contract must
   not regress.
"""

import importlib
import sys

import isardvdi_common.connections.api_sessions as api_sessions
import pytest


@pytest.fixture(autouse=True)
def _reset_provider():
    """Each test starts with no provider registered."""
    yield
    api_sessions._sessions_client_provider = None


# ─────────────────────────────────────────────────────────────────────
# 1. Import side-effect contract
# ─────────────────────────────────────────────────────────────────────


def test_import_does_not_load_grpc_or_protobuf():
    """Importing this module must not pull in grpc or the sessions
    protobuf — both belong to the lazy network-call path. This is the
    primary reason for the dependency-injection refactor: services
    that import the parent ``isardvdi_common`` package transitively
    (change-handler, engine, …) must not pay the gRPC import cost
    when they never call session operations.
    """
    # Re-import in a clean state and verify the lazy boundaries hold
    for mod in [
        "isardvdi_common.connections.api_sessions",
        # Don't reset grpc / sessions_pb2 — those may already be
        # loaded by other apiv4 startup code in the same process.
        # The contract is "this module's top-level imports don't
        # introduce them", which we assert by checking only the
        # *module's own* imports below.
    ]:
        sys.modules.pop(mod, None)
    importlib.import_module("isardvdi_common.connections.api_sessions")
    # Verify the module-level globals don't include grpc / pb2
    # (lazy imports inside functions don't show up at module scope)
    mod = sys.modules["isardvdi_common.connections.api_sessions"]
    assert "grpc" not in vars(mod), (
        "grpc must not be imported at module level in api_sessions — "
        "lazy imports inside the function bodies keep the dependency "
        "out of the load path of services that don't make session calls"
    )
    assert "sessions_pb2" not in vars(mod), (
        "sessions_pb2 must not be imported at module level — same " "reason as grpc"
    )


def test_import_does_not_load_gevent_corecext():
    """Regression guard for the 2026-05-05 SIGSEGV: importing this
    module must not load ``gevent.libev.corecext``. The previous
    sibling module (``grpc_client``) used to call ``init_gevent()``
    at import time and pulled corecext in transitively. Both
    behaviours are now gone; this test is the canary.
    """
    # We cannot reliably remove gevent from sys.modules if some other
    # module already imported it — but we can assert that *this*
    # module's import does not trigger any new gevent imports.
    before = {m for m in sys.modules if m.startswith("gevent")}
    sys.modules.pop("isardvdi_common.connections.api_sessions", None)
    importlib.import_module("isardvdi_common.connections.api_sessions")
    after = {m for m in sys.modules if m.startswith("gevent")}
    new = after - before
    assert not new, (
        f"importing api_sessions newly loaded gevent modules: {sorted(new)}. "
        "This module must stay gevent-free; init_gevent() was the SIGSEGV "
        "root cause in apiv4 (incident 2026-05-05)."
    )


# ─────────────────────────────────────────────────────────────────────
# 2. Provider not configured → clear runtime error
# ─────────────────────────────────────────────────────────────────────


def test_get_without_configure_raises_clear_runtime_error():
    """Calling ``get`` before ``configure_sessions_client`` must raise
    a RuntimeError that names the function the caller forgot to invoke.
    The opposite contract — silently returning None or raising a
    generic AttributeError on a None object — would make
    misconfiguration look like a routing bug.
    """
    with pytest.raises(RuntimeError) as excinfo:
        api_sessions.get("session-xyz", "10.0.0.1")
    msg = str(excinfo.value)
    assert "configure_sessions_client" in msg
    assert "api_sessions" in msg


def test_get_user_session_id_without_configure_raises():
    with pytest.raises(RuntimeError, match="configure_sessions_client"):
        api_sessions.get_user_session_id("user-abc")


def test_revoke_user_session_without_configure_raises():
    with pytest.raises(RuntimeError, match="configure_sessions_client"):
        api_sessions.revoke_user_session("user-abc")


# ─────────────────────────────────────────────────────────────────────
# 3. Provider invoked on every call
# ─────────────────────────────────────────────────────────────────────


def test_configure_then_get_invokes_provider():
    """The provider closure runs on every call (not memoized at
    registration), so apiv4 can swap the backing stub at runtime
    if needed (e.g., reconnection after a service restart).
    """
    calls = []

    class FakeStub:
        def Get(self, request):
            calls.append(("Get", request.id, request.remote_addr))
            return "session-row-from-fake"

    provider_invocations = []
    fake_stub = FakeStub()

    def provider():
        provider_invocations.append(None)
        return fake_stub

    api_sessions.configure_sessions_client(provider)
    result = api_sessions.get("sess-1", "10.0.0.5")
    assert result == "session-row-from-fake"
    assert len(provider_invocations) == 1
    assert calls == [("Get", "sess-1", "10.0.0.5")]

    # Second call invokes the provider again — proves "no memoization
    # at registration", so a new stub returned by the provider would
    # be picked up immediately.
    api_sessions.get("sess-2", "10.0.0.6")
    assert len(provider_invocations) == 2


@pytest.mark.parametrize("falsy", ["", None, 0])
def test_get_with_falsy_session_id_short_circuits(falsy):
    """Any falsy session_id short-circuits to ``no_session`` without
    calling the provider. Production guard at api_sessions.py
    (``if not session_id: raise no_session``) is value-agnostic — it
    triggers on ``""``, ``None``, ``0``, and any other falsy. Empty
    string is the cookie-missing case the original optimisation
    targeted; ``None`` covers callers that don't pre-validate; ``0``
    is paranoia against accidental int-typed IDs.
    """
    provider_calls = []
    api_sessions.configure_sessions_client(lambda: provider_calls.append(None))

    with pytest.raises(type(api_sessions.no_session)):
        api_sessions.get(falsy, "10.0.0.1")
    assert provider_calls == []  # provider never invoked


# ─────────────────────────────────────────────────────────────────────
# 4. Public Error sentinels are stable
# ─────────────────────────────────────────────────────────────────────


def test_error_sentinels_are_module_level_and_unique():
    """Callers in ``isardvdi_common.lib.users.users.user`` and
    elsewhere compare error *identity* (``e in [expired_session,
    invalid_user]``). The sentinels must therefore be module-level
    constants, identity-stable across imports, and distinct from
    one another.
    """
    sentinels = (
        api_sessions.no_session,
        api_sessions.expired_session,
        api_sessions.invalid_session,
        api_sessions.invalid_user,
    )
    # All distinct identities
    assert len({id(s) for s in sentinels}) == 4
    # All proper Error instances (avoid importing Error directly so
    # this test stays decoupled from helper internals)
    for s in sentinels:
        assert (
            hasattr(s, "type") or hasattr(s, "error_type") or hasattr(s, "args")
        ), f"{s!r} doesn't look like an Error"


def test_sentinel_membership_uses_identity_not_equality():
    """The actual call-site contract — ``revoke_user_session`` at
    ``api_sessions.py:144`` does ``if e in [expired_session, invalid_user]``.
    That ``in`` operator goes through ``__eq__``, not ``is``. The
    sentinels must therefore satisfy ``e in [e]`` for the same
    instance and ``e not in [other]`` for different instances —
    otherwise revocation would either skip on unrelated errors or
    fail to skip on the intended ones.

    Independent of ``id()`` distinctness (covered above): two errors
    could have different ids but compare equal via a custom
    ``__eq__``, breaking the membership semantics callers rely on.
    """
    no, expired, invalid_s, invalid_u = (
        api_sessions.no_session,
        api_sessions.expired_session,
        api_sessions.invalid_session,
        api_sessions.invalid_user,
    )

    # Each sentinel is a member of a list containing itself.
    assert no in [no]
    assert expired in [expired]
    assert invalid_s in [invalid_s]
    assert invalid_u in [invalid_u]

    # Cross-membership: each sentinel is NOT in a list of the others.
    assert no not in [expired, invalid_s, invalid_u]
    assert expired not in [no, invalid_s, invalid_u]
    assert invalid_s not in [no, expired, invalid_u]
    assert invalid_u not in [no, expired, invalid_s]

    # The exact production usage from revoke_user_session.
    assert expired in [expired, invalid_u]
    assert invalid_u in [expired, invalid_u]
    assert no not in [expired, invalid_u]


def test_error_sentinels_carry_expected_metadata():
    """Each sentinel carries the HTTP status + description that the
    apiv4 error handler maps. Guards against an accidental refactor
    that swaps ``unauthorized`` → ``not_found`` etc., which would
    silently change the response code seen by the frontend.

    Reads the runtime shape of ``Error`` instances (``status_code``
    integer + ``error`` dict with ``description``) — see
    ``isardvdi_common.helpers.error_factory.ErrorBase``.
    """
    assert api_sessions.no_session.status_code == 401
    assert "No session" in api_sessions.no_session.error["description"]

    assert api_sessions.expired_session.status_code == 401
    assert "expired" in api_sessions.expired_session.error["description"].lower()

    assert api_sessions.invalid_session.status_code == 500
    assert "Invalid session" in api_sessions.invalid_session.error["description"]

    assert api_sessions.invalid_user.status_code == 401
    assert "Invalid user" in api_sessions.invalid_user.error["description"]
