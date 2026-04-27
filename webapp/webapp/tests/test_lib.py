#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import MagicMock

import pytest
from flask import Flask, g

from webapp.lib.flask_rethink import RDB
from webapp.lib.load_config import load_config, loadConfig

# ──────────────────────────────────────────────────────────────────────
# load_config — env-var driven Flask config loader
# ──────────────────────────────────────────────────────────────────────


def test_load_config_returns_log_level_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert load_config() == {"LOG_LEVEL": "DEBUG"}


def test_load_config_defaults_log_level_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert load_config() == {"LOG_LEVEL": "INFO"}


def test_loadconfig_init_app_sets_required_keys(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "test-host")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    fresh = Flask(__name__)
    cfg = loadConfig()

    assert cfg.init_app(fresh) is True
    assert fresh.config["HOSTNAME"] == "test-host"
    assert fresh.config["SESSION_COOKIE_NAME"] == "isard-admin"
    assert fresh.config["LOG_LEVEL"] == "DEBUG"
    assert fresh.config["url"] == "http://www.isardvdi.com:5050"
    assert fresh.debug is True


def test_loadconfig_init_app_defaults_log_level_to_info(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "test-host")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    fresh = Flask(__name__)

    loadConfig().init_app(fresh)

    assert fresh.config["LOG_LEVEL"] == "INFO"
    assert fresh.debug is False


def test_loadconfig_init_app_calls_exit_when_hostname_missing(monkeypatch):
    monkeypatch.delenv("HOSTNAME", raising=False)
    fresh = Flask(__name__)

    # The except block calls exit() which raises SystemExit.
    with pytest.raises(SystemExit):
        loadConfig().init_app(fresh)


# ──────────────────────────────────────────────────────────────────────
# RDB — Flask extension wrapper for RethinkDB pool
# ──────────────────────────────────────────────────────────────────────


def test_rdb_init_with_app_registers_teardown():
    fresh = Flask(__name__)
    fresh.config.update(
        RETHINKDB_HOST="db",
        RETHINKDB_PORT=28015,
        RETHINKDB_DB="isard",
    )

    rdb = RDB(fresh)

    assert rdb.app is fresh
    assert fresh.teardown_appcontext_funcs, "teardown handler must be registered"


def test_rdb_init_without_app_skips_init():
    """RDB() with no app must not register teardown — used in lazy-init code paths."""
    rdb = RDB()
    assert rdb.app is None
    assert rdb.db is None


def test_rdb_conn_caches_per_request_context(monkeypatch):
    fresh = Flask(__name__)
    fresh.config.update(
        RETHINKDB_HOST="db",
        RETHINKDB_PORT=28015,
        RETHINKDB_DB="isard",
        RETHINKDB_AUTH=None,
    )
    fake_conn = MagicMock(name="conn")
    fake_r = MagicMock()
    fake_r.connect.return_value = fake_conn
    monkeypatch.setattr("webapp.lib.flask_rethink.r", fake_r)

    rdb = RDB(fresh)
    with fresh.app_context():
        assert rdb.conn is fake_conn
        # Second access in the same context must return the cached connection.
        assert rdb.conn is fake_conn
        assert g.rethinkdb is fake_conn

    fake_r.connect.assert_called_once_with(
        host="db", port=28015, auth_key=None, db="isard"
    )


def test_rdb_conn_uses_explicit_db_when_provided(monkeypatch):
    fresh = Flask(__name__)
    fresh.config.update(
        RETHINKDB_HOST="db",
        RETHINKDB_PORT=28015,
        RETHINKDB_DB="default-db",
    )
    fake_r = MagicMock()
    fake_r.connect.return_value = MagicMock()
    monkeypatch.setattr("webapp.lib.flask_rethink.r", fake_r)

    rdb = RDB(fresh, db="override-db")
    with fresh.app_context():
        _ = rdb.conn

    args, kwargs = fake_r.connect.call_args
    assert kwargs["db"] == "override-db"


def test_rdb_teardown_closes_connection():
    fresh = Flask(__name__)
    fresh.config.update(
        RETHINKDB_HOST="db",
        RETHINKDB_PORT=28015,
        RETHINKDB_DB="isard",
    )
    RDB(fresh)
    fake_conn = MagicMock()
    teardown = fresh.teardown_appcontext_funcs[-1]

    with fresh.app_context():
        g.rethinkdb = fake_conn

    fake_conn.close.assert_called_once()


def test_rdb_teardown_noop_without_connection():
    fresh = Flask(__name__)
    RDB(fresh)
    teardown = fresh.teardown_appcontext_funcs[-1]

    # Without g.rethinkdb set, the teardown must run without raising.
    with fresh.app_context():
        pass  # context exit triggers teardown with rethinkdb missing
