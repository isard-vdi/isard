# SPDX-License-Identifier: AGPL-3.0-or-later
"""The startup database probe closes the connection it opens."""

import types
from unittest.mock import MagicMock

from scheduler.lib import load_config


def _app():
    return types.SimpleNamespace(
        config={
            "RETHINKDB_HOST": "isard-db",
            "RETHINKDB_PORT": "28015",
            "RETHINKDB_DB": "isard",
        }
    )


def test_check_db_closes_its_connection(monkeypatch, tmp_path):
    fake_r = MagicMock()
    conn = MagicMock()
    fake_r.connect.return_value = conn
    fake_r.db.return_value.table_list.return_value.run.return_value = ["config"]
    monkeypatch.setattr(load_config, "r", fake_r)
    monkeypatch.setattr(load_config, "app", _app())
    monkeypatch.chdir(tmp_path)

    load_config.loadConfig().check_db()

    conn.close.assert_called_once()
