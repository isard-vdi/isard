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

from unittest.mock import patch

import grpc
import isardvdi_common.helpers.bastion as bastion_module
import pytest


@pytest.fixture(autouse=True)
def _reset_provider():
    """Each test starts with no provider registered."""
    yield
    bastion_module._haproxy_bastion_client_provider = None


class _FakeRpcError(grpc.RpcError):
    """grpc.RpcError subclass with the ``code()`` / ``details()``
    methods the retry loop reads. The real grpc internals raise
    ``_InactiveRpcError`` (private), which we can't construct
    portably across grpcio versions — this stand-in matches the
    public surface the production code actually uses.
    """

    def __init__(self, code, details=""):
        super().__init__(details)
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


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


# ─────────────────────────────────────────────────────────────────────
# 4. ``_call_grpc_with_infinite_retry`` semantics
#
# The retry helper is used by every Bastion call site that talks to
# haproxy-sync. Its contract:
#
#   - Success on first try → return result, no retries.
#   - ``grpc.RpcError`` with ``UNAVAILABLE`` → retry with exponential
#     backoff (capped at max_delay), up to max_retries.
#   - ``grpc.RpcError`` with any other code → re-raise immediately,
#     no retry. (Logical errors shouldn't trigger backoff.)
#   - Exhausted max_retries on UNAVAILABLE → raise.
#
# Provider-registration tests above don't exercise this path; this
# block does.
# ─────────────────────────────────────────────────────────────────────


def test_retry_succeeds_on_first_try_no_sleep():
    """Happy path: function returns successfully on first invocation,
    helper returns its result without sleeping or retrying.
    """
    calls = []

    def func(*a, **kw):
        calls.append(kw)
        return "ok"

    with patch.object(bastion_module.time, "sleep") as mock_sleep:
        result = bastion_module.Bastion._call_grpc_with_infinite_retry(func)

    assert result == "ok"
    assert len(calls) == 1
    # Helper passes wait_for_ready=True, timeout=30 to the underlying
    # gRPC call — pin that contract too, since haproxy-sync's stub
    # depends on those defaults.
    assert calls[0].get("wait_for_ready") is True
    assert calls[0].get("timeout") == 30
    mock_sleep.assert_not_called()


def test_retry_backs_off_on_unavailable_then_succeeds():
    """``UNAVAILABLE`` triggers exponential backoff with the
    documented schedule (1, 2, 4, 8, … capped at max_delay). Verify
    by failing N times then succeeding, asserting the sleep deltas
    match the schedule.
    """
    attempts = []
    sleeps = []

    def flaky_func(*a, **kw):
        attempts.append(None)
        if len(attempts) < 4:
            raise _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "service starting")
        return "ok-after-retries"

    with patch.object(bastion_module.time, "sleep", side_effect=sleeps.append):
        result = bastion_module.Bastion._call_grpc_with_infinite_retry(
            flaky_func, initial_delay=1, max_delay=30, max_retries=10
        )

    assert result == "ok-after-retries"
    assert len(attempts) == 4  # 3 fails + 1 success
    # Sleeps after attempts 1, 2, 3 (not after the success on 4).
    assert sleeps == [1, 2, 4]


def test_retry_caps_backoff_at_max_delay():
    """Long-running outage: backoff doubles until ``max_delay`` then
    stays flat. Configure ``initial_delay=1, max_delay=4`` and force
    enough failures to exceed the cap; assert the schedule plateaus.
    """
    sleeps = []
    call_count = {"n": 0}

    def always_unavailable(*a, **kw):
        call_count["n"] += 1
        raise _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down")

    with patch.object(bastion_module.time, "sleep", side_effect=sleeps.append):
        with pytest.raises(_FakeRpcError):
            bastion_module.Bastion._call_grpc_with_infinite_retry(
                always_unavailable,
                initial_delay=1,
                max_delay=4,
                max_retries=6,
            )

    # 6 attempts → 5 sleeps (last failure raises without sleeping).
    # Schedule: 1, 2, 4, 4, 4 — capped at max_delay=4.
    assert sleeps == [1, 2, 4, 4, 4]
    assert call_count["n"] == 6


def test_retry_does_not_retry_on_non_unavailable_codes():
    """Logical errors (``INVALID_ARGUMENT``, ``PERMISSION_DENIED``,
    ``NOT_FOUND``, …) are not transient; retrying just hides the
    bug. The helper must re-raise immediately on anything except
    ``UNAVAILABLE``.
    """
    sleeps = []
    call_count = {"n": 0}

    def invalid_arg(*a, **kw):
        call_count["n"] += 1
        raise _FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT, "domain malformed")

    with patch.object(bastion_module.time, "sleep", side_effect=sleeps.append):
        with pytest.raises(_FakeRpcError) as excinfo:
            bastion_module.Bastion._call_grpc_with_infinite_retry(invalid_arg)

    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert call_count["n"] == 1  # raised on first attempt, no retry
    assert sleeps == []  # no backoff for logical errors


def test_retry_raises_after_exhausting_max_retries_on_unavailable():
    """If the dependency stays ``UNAVAILABLE`` past ``max_retries``,
    the helper gives up and propagates the error so callers can
    fail explicitly rather than block forever.
    """
    call_count = {"n": 0}

    def perpetually_down(*a, **kw):
        call_count["n"] += 1
        raise _FakeRpcError(grpc.StatusCode.UNAVAILABLE, "down")

    with patch.object(bastion_module.time, "sleep"):
        with pytest.raises(_FakeRpcError) as excinfo:
            bastion_module.Bastion._call_grpc_with_infinite_retry(
                perpetually_down,
                initial_delay=1,
                max_delay=2,
                max_retries=3,
            )

    assert excinfo.value.code() == grpc.StatusCode.UNAVAILABLE
    assert call_count["n"] == 3  # exactly max_retries attempts


# ─────────────────────────────────────────────────────────────────────
# 5. ``readable_sync_error`` — pure regex extraction
#
# haproxy-sync wraps ACME's stdout/stderr in DomainSyncError.error.
# When ACME rejects a certificate the payload embeds a JSON object
# with a ``"detail"`` field. The helper surfaces that detail to
# webapp/admin UIs so users see "DNS challenge failed" instead of
# 50 lines of shell log dump.
# ─────────────────────────────────────────────────────────────────────


def test_readable_sync_error_extracts_detail_from_acme_json():
    """Typical ACME rejection — JSON object embedded in the raw
    stdout/stderr. The regex pulls the ``"detail"`` value.
    """
    raw = (
        "+ acme.sh --issue ...\n"
        '{"type":"urn:acme:error:unauthorized",'
        '"detail":"DNS-01 challenge failed for example.com",'
        '"status":403}'
    )
    assert (
        bastion_module.Bastion.readable_sync_error(raw)
        == "DNS-01 challenge failed for example.com"
    )


def test_readable_sync_error_handles_escaped_quotes():
    """ACME sometimes embeds escaped quotes in ``detail`` (e.g.
    when the failing domain itself appears in the message). The
    regex must accept ``\\"`` inside the quoted body.
    """
    raw = '{"detail":"Domain \\"foo.bar\\" is not authorized","status":403}'
    # ``unicode_escape`` decode unwraps the escaped quotes.
    result = bastion_module.Bastion.readable_sync_error(raw)
    assert 'Domain "foo.bar" is not authorized' == result


def test_readable_sync_error_returns_raw_when_no_detail_present():
    """No JSON / no ``detail`` field — fall back to the raw string
    so the caller still sees something rather than empty output.
    Pin this so a future "make the regex stricter" refactor
    doesn't silently drop unstructured errors.
    """
    raw = "Some plain stderr message that is not JSON"
    assert bastion_module.Bastion.readable_sync_error(raw) == raw


def test_readable_sync_error_empty_input_returns_empty():
    """Defensive: empty / None input returns empty string so the
    caller (typically webapp template rendering) doesn't print
    ``None`` literally.
    """
    assert bastion_module.Bastion.readable_sync_error("") == ""
    assert bastion_module.Bastion.readable_sync_error(None) == ""


# ─────────────────────────────────────────────────────────────────────
# 6. Cache-backed read methods
#
# ``bastion_enabled_in_db``, ``get_bastion_domain``, and
# ``bastion_domain_verification_required`` all read through
# ``Caches.get_document``. They're invoked on the auth hot path
# (every desktop with a bastion target needs the domain), so the
# fallback / default behaviour matters.
# ─────────────────────────────────────────────────────────────────────


def test_bastion_enabled_in_db_returns_cached_flag(monkeypatch):
    """Reads ``config[1].bastion.enabled``. ``Caches.get_document``
    with a single key returns the unwrapped *value* (the same
    contract that the deployment-permissions bug-fix codified
    in models/deployment.py); production code does ``.get("enabled")``
    on the result, so the cached value is the dict, not the unwrapped
    bool.
    """
    cached = {"enabled": True, "domain": "bastion.example.com"}
    captured = []

    def fake_get_document(table, item_id, keys=None, invalidate=False):
        captured.append((table, item_id, tuple(keys or ())))
        return cached

    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(lambda cls, *a, **kw: fake_get_document(*a, **kw)),
    )

    assert bastion_module.Bastion.bastion_enabled_in_db() is True
    # Verifies the read shape — config table, single row id 1, ["bastion"]
    # selector. Locks the contract that callers / Caches both depend on.
    assert captured == [("config", 1, ("bastion",))]


def test_get_bastion_domain_returns_category_override_when_set(monkeypatch):
    """When the category has its own bastion_domain, the helper
    returns it without falling back to the global config.
    """
    calls = []

    def fake_get_document(table, item_id, keys=None, invalidate=False):
        calls.append((table, item_id))
        if table == "categories":
            return "tenant.example.com"
        # Should not be reached when the category has a domain.
        raise AssertionError(
            "Should not query config when categories has its own domain"
        )

    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(lambda cls, *a, **kw: fake_get_document(*a, **kw)),
    )

    result = bastion_module.Bastion.get_bastion_domain("tenant-a")
    assert result == "tenant.example.com"
    assert calls == [("categories", "tenant-a")]


def test_get_bastion_domain_falls_back_to_config_when_category_unset(monkeypatch):
    """No per-category override -> read the global default from
    ``config[1].bastion.domain``.
    """
    calls = []

    def fake_get_document(table, item_id, keys=None, invalidate=False):
        calls.append((table, item_id))
        if table == "categories":
            return None  # category has no bastion_domain
        if table == "config":
            return {"enabled": True, "domain": "bastion.global.example.com"}
        raise AssertionError(f"unexpected table {table}")

    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(lambda cls, *a, **kw: fake_get_document(*a, **kw)),
    )

    result = bastion_module.Bastion.get_bastion_domain("tenant-b")
    assert result == "bastion.global.example.com"
    # Both reads happened in the documented order: category first, then config.
    assert calls == [("categories", "tenant-b"), ("config", 1)]


def test_get_bastion_domain_no_category_id_uses_config_only(monkeypatch):
    """Calling without a category_id skips the category read
    entirely. Pins the optimization for global-config-only callers.
    """
    calls = []

    def fake_get_document(table, item_id, keys=None, invalidate=False):
        calls.append((table, item_id))
        if table == "config":
            return {"enabled": True, "domain": "bastion.example.com"}
        raise AssertionError(f"unexpected table {table}")

    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(lambda cls, *a, **kw: fake_get_document(*a, **kw)),
    )

    result = bastion_module.Bastion.get_bastion_domain()
    assert result == "bastion.example.com"
    assert calls == [("config", 1)]  # category never queried


def test_bastion_domain_verification_required_defaults_true(monkeypatch):
    """Cache returns a bastion config where ``domain_verification_required``
    is unset -> default True. The default matters because new
    installs that don't ship the field shouldn't accidentally
    bypass DNS verification.
    """
    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(lambda cls, *a, **kw: {"enabled": True}),
    )
    assert bastion_module.Bastion.bastion_domain_verification_required() is True


def test_bastion_domain_verification_required_returns_false_when_disabled(monkeypatch):
    """Explicitly set False -> respect it, don't snap back to the
    default. Pins both branches so a future refactor that swaps
    ``.get("...", True)`` -> ``.get("...")`` (default None ->
    treated as False elsewhere) breaks loud.
    """
    monkeypatch.setattr(
        "isardvdi_common.helpers.bastion.Caches.get_document",
        classmethod(
            lambda cls, *a, **kw: {
                "enabled": True,
                "domain_verification_required": False,
            }
        ),
    )
    assert bastion_module.Bastion.bastion_domain_verification_required() is False
