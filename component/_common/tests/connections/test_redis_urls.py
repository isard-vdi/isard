# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib

import pytest


@pytest.fixture
def redis_urls(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    import isardvdi_common.connections.redis_urls as module

    return importlib.reload(module)


class TestConstants:
    def test_db_layout(self, redis_urls):
        assert redis_urls.RQ_DB == 0
        assert redis_urls.SESSIONS_DB == 1
        assert redis_urls.CHANGEFEED_DB == 2
        assert redis_urls.SOCKETIO_DB == 3

    def test_constants_are_unique(self, redis_urls):
        assert (
            len(
                {
                    redis_urls.RQ_DB,
                    redis_urls.SESSIONS_DB,
                    redis_urls.CHANGEFEED_DB,
                    redis_urls.SOCKETIO_DB,
                }
            )
            == 4
        )


class TestBaseUrl:
    def test_defaults_when_no_env(self, redis_urls):
        assert redis_urls._base_url() == "redis://:@isard-redis:6379"

    def test_uses_triple_when_set(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_HOST", "custom-host")
        monkeypatch.setenv("REDIS_PORT", "6380")
        monkeypatch.setenv("REDIS_PASSWORD", "secret")
        assert redis_urls._base_url() == "redis://:secret@custom-host:6380"

    def test_empty_string_env_falls_back_to_defaults(self, monkeypatch, redis_urls):
        # Docker compose injects a bare pass-through key as an empty string, and
        # os.environ.get(k, default) returns "" for it, so the code uses `or`.
        monkeypatch.setenv("REDIS_HOST", "")
        monkeypatch.setenv("REDIS_PORT", "")
        monkeypatch.setenv("REDIS_PASSWORD", "")
        assert redis_urls._base_url() == "redis://:@isard-redis:6379"

    def test_redis_url_wins_over_triple(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_URL", "redis://:override@other-host:1234")
        monkeypatch.setenv("REDIS_HOST", "ignored")
        monkeypatch.setenv("REDIS_PORT", "9999")
        monkeypatch.setenv("REDIS_PASSWORD", "ignored-too")
        assert redis_urls._base_url() == "redis://:override@other-host:1234"


class TestWithDb:
    def test_appends_db_to_default_base(self, redis_urls):
        assert redis_urls._with_db(7) == "redis://:@isard-redis:6379/7"

    def test_replaces_existing_db_path(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_URL", "redis://:pwd@host:6379/9")
        assert redis_urls._with_db(2) == "redis://:pwd@host:6379/2"


class TestHelperFunctions:
    def test_rq_url_uses_db_0(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_PORT", "6379")
        monkeypatch.setenv("REDIS_PASSWORD", "p")
        assert redis_urls.rq_url() == "redis://:p@h:6379/0"

    def test_changefeed_url_uses_db_2(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_PORT", "6379")
        monkeypatch.setenv("REDIS_PASSWORD", "p")
        assert redis_urls.changefeed_url() == "redis://:p@h:6379/2"

    def test_socketio_url_uses_db_3(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_HOST", "h")
        monkeypatch.setenv("REDIS_PORT", "6379")
        monkeypatch.setenv("REDIS_PASSWORD", "p")
        assert redis_urls.socketio_url() == "redis://:p@h:6379/3"

    def test_helpers_share_base_url(self, monkeypatch, redis_urls):
        monkeypatch.setenv("REDIS_URL", "redis://:shared@bus:6400")
        assert redis_urls.rq_url() == "redis://:shared@bus:6400/0"
        assert redis_urls.changefeed_url() == "redis://:shared@bus:6400/2"
        assert redis_urls.socketio_url() == "redis://:shared@bus:6400/3"
