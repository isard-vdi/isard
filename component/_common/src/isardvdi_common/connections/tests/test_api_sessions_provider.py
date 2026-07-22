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
from unittest.mock import MagicMock

import grpc
import isardvdi_common.connections.api_sessions as api_sessions
import pytest


@pytest.fixture(autouse=True)
def _reset_provider():
    """Each test starts with no provider registered."""
    yield
    api_sessions._sessions_client_provider = None


class _FakeRpcError(grpc.RpcError):
    """grpc.RpcError stand-in with the ``code()`` method the
    production translation logic reads. The real grpc internals
    raise private ``_InactiveRpcError``; mirror only the public
    surface so tests stay portable across grpcio versions.
    """

    def __init__(self, code):
        super().__init__()
        self._code = code

    def code(self):
        return self._code

    def details(self):
        return ""


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


# ─────────────────────────────────────────────────────────────────────
# 5. gRPC error -> Error sentinel translation
#
# Every authenticated apiv4 request resolves through ``get`` (session
# lookup) on the hot path; logout / user-deletion / role-change
# flows resolve through ``revoke_user_session``. The translation
# from gRPC ``StatusCode`` to the public ``Error`` sentinels is the
# contract the rest of the stack reads — a regression here surfaces
# as the wrong HTTP code on the frontend (401 vs 500) which is
# user-visible.
#
# Provider tests above cover registration / unconfigured / lazy
# import. These cover the post-registration error translation that
# the original suite skipped.
# ─────────────────────────────────────────────────────────────────────


def _configure_stub(stub):
    """Helper: register ``stub`` as the sessions client provider so
    the production code path picks it up via ``_client()``."""
    api_sessions.configure_sessions_client(lambda: stub)


# --- get(session_id, remote_addr) ---


def test_get_translates_grpc_not_found_to_expired_session():
    """``NOT_FOUND`` from the sessions service means the session id
    has no row — semantically the user's session expired. Map to
    ``expired_session`` so the frontend shows "please log in
    again" (401), not "internal server error" (500).
    """
    stub = MagicMock()
    stub.Get.side_effect = _FakeRpcError(grpc.StatusCode.NOT_FOUND)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.expired_session)) as excinfo:
        api_sessions.get("sess-gone", "10.0.0.1")
    assert excinfo.value is api_sessions.expired_session


def test_get_translates_grpc_unauthenticated_to_expired_session():
    """``UNAUTHENTICATED`` from the sessions service means the
    presented credentials don't match a live session — also
    ``expired_session``. Distinct from ``NOT_FOUND`` semantically
    but the user-facing outcome is the same: re-authenticate.
    """
    stub = MagicMock()
    stub.Get.side_effect = _FakeRpcError(grpc.StatusCode.UNAUTHENTICATED)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.expired_session)) as excinfo:
        api_sessions.get("sess-bad-token", "10.0.0.1")
    assert excinfo.value is api_sessions.expired_session


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.INTERNAL,
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
    ],
)
def test_get_translates_other_grpc_codes_to_invalid_session(code):
    """Anything that isn't ``NOT_FOUND`` / ``UNAUTHENTICATED`` is a
    real backend failure, not a session-state issue — surface as
    ``invalid_session`` (500) so it shows up in the 5xx alert
    pages and isn't misread as a credentials problem.
    """
    stub = MagicMock()
    stub.Get.side_effect = _FakeRpcError(code)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.invalid_session)) as excinfo:
        api_sessions.get("sess-x", "10.0.0.1")
    assert excinfo.value is api_sessions.invalid_session


# --- get_user_session_id(user_id) ---


def test_get_user_session_id_returns_provider_response_on_success():
    """Happy path: the response from the gRPC stub passes through
    unchanged. Pin this so a future refactor that wraps the
    response (e.g. .data, .id) breaks loud.
    """
    response = MagicMock()
    response.id = "session-row-abc"
    stub = MagicMock()
    stub.GetUserSession.return_value = response
    _configure_stub(stub)

    result = api_sessions.get_user_session_id("user-123")
    assert result is response
    assert result.id == "session-row-abc"
    stub.GetUserSession.assert_called_once()


def test_get_user_session_id_translates_not_found_to_expired_session():
    """User exists in our DB but has no live session row — they're
    logged out. ``expired_session`` is the right user-facing
    outcome (401 "please log in again").
    """
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(grpc.StatusCode.NOT_FOUND)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.expired_session)) as excinfo:
        api_sessions.get_user_session_id("user-no-session")
    assert excinfo.value is api_sessions.expired_session


def test_get_user_session_id_translates_invalid_argument_to_invalid_user():
    """``INVALID_ARGUMENT`` from the sessions service means the user
    id format is bogus or doesn't match any user — distinct from
    "no live session" (NOT_FOUND). Map to ``invalid_user`` (401)
    so callers can branch on identity-resolution vs session-state.
    """
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.invalid_user)) as excinfo:
        api_sessions.get_user_session_id("not-a-real-user")
    assert excinfo.value is api_sessions.invalid_user


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.INTERNAL,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    ],
)
def test_get_user_session_id_translates_other_codes_to_invalid_session(code):
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(code)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.invalid_session)) as excinfo:
        api_sessions.get_user_session_id("user-x")
    assert excinfo.value is api_sessions.invalid_session


# --- revoke_user_session(user_id) ---
#
# This function has a try/except over BOTH the inner
# ``get_user_session_id`` call AND the outer ``Revoke`` call. The
# semantic contract:
#
#   1. If the user has no live session (``expired_session``) or no
#      such user (``invalid_user``), revocation is a no-op — return
#      silently. The desired post-state (no live session) already
#      holds.
#   2. If the inner Get raises any *other* Error, propagate.
#   3. If the outer Revoke RPC succeeds, return its response.
#   4. If the outer Revoke RPC raises ``NOT_FOUND`` (the session
#      was deleted between Get and Revoke — race condition), the
#      desired post-state holds; return silently.
#   5. If the outer Revoke RPC raises any other code, surface as
#      ``invalid_session``.


def test_revoke_user_session_silent_when_user_has_expired_session():
    """``get_user_session_id`` raises ``expired_session`` ->
    revocation goal already achieved (no live session) -> return.
    """
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(grpc.StatusCode.NOT_FOUND)
    _configure_stub(stub)

    # Must not raise; must not call Revoke either (nothing to revoke).
    result = api_sessions.revoke_user_session("user-already-logged-out")
    assert result is None
    stub.Revoke.assert_not_called()


def test_revoke_user_session_silent_when_user_id_invalid():
    """``get_user_session_id`` raises ``invalid_user`` -> the user
    doesn't exist, so there's nothing to revoke. Don't fail
    user-deletion flows on a bogus id; let them proceed.
    """
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT)
    _configure_stub(stub)

    result = api_sessions.revoke_user_session("not-a-real-user")
    assert result is None
    stub.Revoke.assert_not_called()


def test_revoke_user_session_propagates_unexpected_inner_error():
    """If ``get_user_session_id`` raises anything other than the two
    expected sentinels, the inner ``except Error`` re-raises it.
    Exercise via UNAVAILABLE on GetUserSession (which the helper
    translates to ``invalid_session``).
    """
    stub = MagicMock()
    stub.GetUserSession.side_effect = _FakeRpcError(grpc.StatusCode.UNAVAILABLE)
    _configure_stub(stub)

    # The inner ``except Error: raise e`` propagates the Error through
    # the outer try/except (which only catches ``grpc.RpcError``,
    # not ``Error``), so the caller sees ``invalid_session``.
    with pytest.raises(type(api_sessions.invalid_session)):
        api_sessions.revoke_user_session("user-x")


def test_revoke_user_session_returns_revoke_response_on_success():
    """Happy path: GetUserSession returns a session, Revoke returns
    its response. Must propagate the Revoke response so callers
    that read it (e.g. for audit logging) see the right shape.
    """
    get_resp = MagicMock()
    get_resp.id = "sess-to-kill"
    revoke_resp = MagicMock(name="RevokeResponse")
    stub = MagicMock()
    stub.GetUserSession.return_value = get_resp
    stub.Revoke.return_value = revoke_resp
    _configure_stub(stub)

    result = api_sessions.revoke_user_session("user-1")
    assert result is revoke_resp
    stub.Revoke.assert_called_once()


def test_revoke_user_session_silent_when_revoke_returns_not_found():
    """Race condition: between GetUserSession and Revoke another
    process deleted the session. ``Revoke`` raises NOT_FOUND.
    The desired post-state (no live session) already holds, so
    revocation must return silently — not raise ``invalid_session``.

    Without this contract, every call site in
    ``isardvdi_common.lib.users.users.user`` (4 places, no
    try/except around the call) would 500 on the race. The user
    deletion flow at line 1218 is the most user-visible.
    """
    get_resp = MagicMock()
    get_resp.id = "sess-raced"
    stub = MagicMock()
    stub.GetUserSession.return_value = get_resp
    stub.Revoke.side_effect = _FakeRpcError(grpc.StatusCode.NOT_FOUND)
    _configure_stub(stub)

    # Must not raise — the session is already gone, that's the
    # desired post-state of a revocation call.
    result = api_sessions.revoke_user_session("user-raced")
    assert result is None
    stub.Revoke.assert_called_once()


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.INTERNAL,
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    ],
)
def test_revoke_user_session_invalid_session_on_other_revoke_codes(code):
    """Real backend failures from Revoke surface as
    ``invalid_session`` (500). The session-deletion call site sees
    a 5xx and can decide to retry / alert, instead of treating it
    as "session was already gone".
    """
    get_resp = MagicMock()
    get_resp.id = "sess-x"
    stub = MagicMock()
    stub.GetUserSession.return_value = get_resp
    stub.Revoke.side_effect = _FakeRpcError(code)
    _configure_stub(stub)

    with pytest.raises(type(api_sessions.invalid_session)) as excinfo:
        api_sessions.revoke_user_session("user-x")
    assert excinfo.value is api_sessions.invalid_session
