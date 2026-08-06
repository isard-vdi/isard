#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UsersProcessed.user_config``.

Three concerns are covered:

* the cached body depends on the whole identity carried by the token payload
  (user, role, category, group, provider), not on the user id alone;
* the session block is per-request state and must never be served from the
  cached body;
* the storage-quota sync is a side effect with its own per-session bound, so it
  neither rides on the config-cache key nor runs once per request.
"""

from types import SimpleNamespace

import pytest


class _Timestamp:
    def __init__(self, seconds):
        self._seconds = seconds

    def ToSeconds(self):
        return self._seconds


@pytest.fixture
def user_config_env(monkeypatch):
    """Stub every collaborator ``user_config`` reaches out to."""
    from isardvdi_common.lib.users.users import user as mod

    mod.UsersProcessed._user_config_cached.cache_clear()
    mod._user_quota_sync_throttle.clear()

    for var in (
        "FRONTEND_SHOW_BOOKINGS",
        "FRONTEND_SHOW_TEMPORAL",
        "FRONTEND_MODE",
        "FARO_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)

    quota_calls = []
    monkeypatch.setattr(
        mod.UserStorage,
        "isard_user_storage_update_user_quota",
        staticmethod(lambda user_id: quota_calls.append(user_id)),
    )

    monkeypatch.setattr(
        mod,
        "Configuration",
        lambda: SimpleNamespace(smtp={"enabled": True}),
    )
    monkeypatch.setattr(
        mod,
        "Category",
        lambda category_id: SimpleNamespace(manager_permissions={}),
    )

    # Called exactly once per run of the cached body, so it doubles as the
    # counter that tells a cache hit from a miss.
    body_calls = []

    def _fake_get_custom_login_url(category_id):
        body_calls.append(category_id)
        return f"url-{category_id}"

    monkeypatch.setattr(
        mod.CategoriesProcessed,
        "get_custom_login_url",
        staticmethod(_fake_get_custom_login_url),
    )
    monkeypatch.setattr(
        mod.Bastion,
        "get_bastion_domain",
        staticmethod(lambda category_id: f"bastion-{category_id}"),
    )
    # Default: no bastion. Individual tests override to probe a payload field.
    monkeypatch.setattr(
        mod.Helpers, "can_use_bastion", staticmethod(lambda payload: False)
    )
    monkeypatch.setattr(
        mod.Helpers,
        "can_use_bastion_individual_domains",
        staticmethod(lambda payload: False),
    )

    session_calls = []

    def _fake_get_user_session_id(user_id):
        session_calls.append(user_id)
        return SimpleNamespace(
            id=f"session-{user_id}-{len(session_calls)}",
            time=SimpleNamespace(
                max_renew_time=_Timestamp(1000 + len(session_calls)),
                max_time=_Timestamp(2000 + len(session_calls)),
            ),
        )

    monkeypatch.setattr(mod, "get_user_session_id", _fake_get_user_session_id)

    yield SimpleNamespace(
        mod=mod,
        Processed=mod.UsersProcessed,
        quota_calls=quota_calls,
        session_calls=session_calls,
        body_calls=body_calls,
        monkeypatch=monkeypatch,
    )

    mod.UsersProcessed._user_config_cached.cache_clear()
    mod._user_quota_sync_throttle.clear()


def _payload(user_id, **overrides):
    payload = {
        "user_id": user_id,
        "role_id": "user",
        "category_id": "cat-1",
        "group_id": "grp-1",
        "provider": "local",
        "session_id": "browser-session",
    }
    payload.update(overrides)
    return payload


class TestUserConfigMemoization:
    """The cache must still hit; a key that never repeats is a silent
    regression the identity tests below cannot see."""

    def test_identical_payload_runs_the_cached_body_once(self, user_config_env):
        payload = _payload("u-memoized")

        first = user_config_env.Processed.user_config(payload)
        second = user_config_env.Processed.user_config(payload)

        assert user_config_env.body_calls == ["cat-1"]
        assert first["category_custom_url"] == second["category_custom_url"]

    def test_session_id_is_not_part_of_the_cache_key(self, user_config_env):
        user_id = "u-session-not-keyed"

        user_config_env.Processed.user_config(_payload(user_id, session_id="sess-a"))
        user_config_env.Processed.user_config(_payload(user_id, session_id="sess-b"))

        # Keying on session_id would give every login its own entry and would
        # re-introduce the leak the tests below guard against.
        assert user_config_env.body_calls == ["cat-1"]


class TestUserConfigCacheKey:
    def test_service_session_does_not_leak_into_browser_call(self, user_config_env):
        user_id = "u-service-leak"

        service = user_config_env.Processed.user_config(
            _payload(user_id, session_id="isardvdi-service")
        )
        assert service["session"]["id"] == "isardvdi-service"

        browser = user_config_env.Processed.user_config(_payload(user_id))
        assert browser["session"]["id"] != "isardvdi-service"
        assert browser["session"]["max_time"] != 0

    def test_api_key_session_does_not_leak_into_browser_call(self, user_config_env):
        user_id = "u-apikey-leak"

        user_config_env.Processed.user_config(_payload(user_id, session_id="api-key"))
        browser = user_config_env.Processed.user_config(_payload(user_id))
        assert browser["session"]["id"] != "isardvdi-service"

    def test_session_block_is_refreshed_on_every_call(self, user_config_env):
        user_id = "u-session-fresh"

        first = user_config_env.Processed.user_config(_payload(user_id))
        second = user_config_env.Processed.user_config(_payload(user_id))

        # A login revokes the previous session and mints a new one, so the id
        # and the deadlines can differ between two calls that hit the cache.
        assert second["session"]["id"] != first["session"]["id"]
        assert second["session"]["max_renew_time"] != first["session"]["max_renew_time"]
        assert len(user_config_env.session_calls) == 2

    def test_role_change_is_not_served_from_the_previous_role(self, user_config_env):
        user_id = "u-role-change"

        as_admin = user_config_env.Processed.user_config(
            _payload(user_id, role_id="admin")
        )
        as_user = user_config_env.Processed.user_config(
            _payload(user_id, role_id="user")
        )

        assert as_admin["show_bookings_button"] is True
        assert as_user["show_bookings_button"] is False
        assert as_admin["show_gpu_plannings"] is True
        assert as_user["show_gpu_plannings"] is False

    def test_category_change_is_not_served_from_the_previous_category(
        self, user_config_env
    ):
        user_id = "u-category-change"

        first = user_config_env.Processed.user_config(
            _payload(user_id, category_id="cat-a")
        )
        second = user_config_env.Processed.user_config(
            _payload(user_id, category_id="cat-b")
        )

        assert first["category_custom_url"] == "url-cat-a"
        assert second["category_custom_url"] == "url-cat-b"

    def test_group_change_is_not_served_from_the_previous_group(self, user_config_env):
        user_id = "u-group-change"
        # can_use_bastion() runs the payload through Alloweds.is_allowed, which
        # also reads group_id, so the group is part of the identity too.
        user_config_env.monkeypatch.setattr(
            user_config_env.mod.Helpers,
            "can_use_bastion",
            staticmethod(lambda payload: payload["group_id"] == "grp-allowed"),
        )

        allowed = user_config_env.Processed.user_config(
            _payload(user_id, group_id="grp-allowed")
        )
        denied = user_config_env.Processed.user_config(
            _payload(user_id, group_id="grp-denied")
        )

        assert allowed["can_use_bastion"] is True
        assert denied["can_use_bastion"] is False

    def test_provider_change_is_not_served_from_the_previous_provider(
        self, user_config_env
    ):
        user_id = "u-provider-change"
        user_config_env.monkeypatch.setenv(
            "AUTHENTICATION_AUTHENTICATION_SAML_SAVE_EMAIL", "true"
        )

        local = user_config_env.Processed.user_config(
            _payload(user_id, provider="local")
        )
        saml = user_config_env.Processed.user_config(_payload(user_id, provider="saml"))

        assert local["show_change_email_button"] is True
        assert saml["show_change_email_button"] is False


class TestUserConfigQuotaSync:
    def test_first_call_for_a_user_syncs(self, user_config_env):
        user_id = "u-quota-first"

        user_config_env.Processed.user_config(_payload(user_id))

        assert user_config_env.quota_calls == [user_id]

    def test_repeated_requests_in_one_session_sync_once(self, user_config_env):
        user_id = "u-quota-throttled"
        payload = _payload(user_id)

        for _ in range(5):
            user_config_env.Processed.user_config(payload)

        # The sync spawns an unpooled thread that does an HTTP round-trip plus
        # a database write; token renewals and cross-tab config refetches must
        # not multiply it.
        assert user_config_env.quota_calls == [user_id]

    def test_config_cache_miss_does_not_re_trigger_the_sync(self, user_config_env):
        user_id = "u-quota-not-on-config-key"

        user_config_env.Processed.user_config(_payload(user_id, category_id="cat-a"))
        user_config_env.Processed.user_config(_payload(user_id, category_id="cat-b"))

        # Two distinct config-cache entries, one sync: the throttle is keyed on
        # the session, not on whatever the config key happens to contain.
        assert user_config_env.body_calls == ["cat-a", "cat-b"]
        assert user_config_env.quota_calls == [user_id]

    def test_a_new_session_syncs_again_despite_a_config_cache_hit(
        self, user_config_env
    ):
        user_id = "u-quota-relogin"

        user_config_env.Processed.user_config(_payload(user_id, session_id="sess-a"))
        user_config_env.Processed.user_config(_payload(user_id, session_id="sess-b"))

        # Re-login: the config body is served from the cache, but the sync that
        # the provider expects at login still runs.
        assert user_config_env.body_calls == ["cat-1"]
        assert user_config_env.quota_calls == [user_id, user_id]

    def test_throttle_expiry_lets_the_sync_run_again(self, user_config_env):
        user_id = "u-quota-ttl"
        payload = _payload(user_id)

        user_config_env.Processed.user_config(payload)
        user_config_env.Processed.user_config(payload)
        assert user_config_env.quota_calls == [user_id]

        # Expire the throttle window without sleeping on it.
        user_config_env.mod._user_quota_sync_throttle.clear()

        user_config_env.Processed.user_config(payload)
        assert user_config_env.quota_calls == [user_id, user_id]

    def test_sync_is_bounded_across_concurrent_requests(self, user_config_env):
        import threading

        user_id = "u-quota-concurrent"
        payload = _payload(user_id)
        start = threading.Barrier(8)

        def _call():
            start.wait()
            user_config_env.Processed.user_config(payload)

        threads = [threading.Thread(target=_call) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # cachetools' @cached runs the wrapped function outside its lock, so a
        # decorator-based guard would let every racing miss through. The
        # throttle claims its slot under the lock instead.
        assert user_config_env.quota_calls == [user_id]
