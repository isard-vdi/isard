# SPDX-License-Identifier: AGPL-3.0-or-later
"""The config-readiness probe closes the socket it opens."""

import importlib.util
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from tests.helpers import ENGINE_SRC


@pytest.fixture
def probe(monkeypatch):
    db = types.ModuleType("engine.services.db.db")

    @contextmanager
    def rethink_conn():
        yield MagicMock()

    db.rethink_conn = rethink_conn
    monkeypatch.setitem(sys.modules, "engine.services.db.db", db)
    spec = importlib.util.spec_from_file_location(
        "engine_db_config_probe", str(ENGINE_SRC / "services" / "db" / "config.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fake_r = MagicMock()
    probe_conn = MagicMock()
    fake_r.connect.return_value = probe_conn
    monkeypatch.setattr(mod, "r", fake_r)
    return mod, fake_r, probe_conn


def test_missing_database_closes_the_probe_socket(probe):
    mod, fake_r, probe_conn = probe
    fake_r.db_list.return_value.contains.return_value.run.return_value = False

    assert mod.table_config_created_and_populated() is False
    probe_conn.close.assert_called_once()


def test_present_database_closes_the_probe_socket(probe):
    mod, fake_r, probe_conn = probe
    fake_r.db_list.return_value.contains.return_value.run.return_value = True
    fake_r.table_list.return_value.contains.return_value.run.return_value = True
    fake_r.table.return_value.get.return_value.run.return_value = {"id": 1}

    assert mod.table_config_created_and_populated() is True
    probe_conn.close.assert_called_once()


def test_failing_probe_query_still_closes_the_socket(probe):
    mod, fake_r, probe_conn = probe
    fake_r.db_list.return_value.contains.return_value.run.side_effect = RuntimeError

    assert mod.table_config_created_and_populated() is False
    probe_conn.close.assert_called_once()
