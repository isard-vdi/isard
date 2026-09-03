#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A desktop whose address has not arrived must not take the service down.

``init_domains_started`` runs from ``UserIpTools.__init__``, which runs from
``Wg.__init__``, which runs at import. Anything it raises kills the vpn service
before it reaches its changefeed loop, and it comes straight back up to do the
same again: nobody's vpn works, and the reason is one desktop's row.

A domain between Started and its address arriving carries ``viewer.guest_ip``
as an explicit null. The old guard asked whether the key was present, which it
is, so the null reached the log line that concatenates it and raised TypeError
outside the try that wraps the user lookup.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

STARTED = [
    {"id": "no-viewer-yet", "user": "u1", "viewer": {}},
    {"id": "address-not-arrived", "user": "u2", "viewer": {"guest_ip": None}},
    {"id": "running", "user": "u3", "viewer": {"guest_ip": "10.2.0.9"}},
]


class _FakeR:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return self

    def get_all(self, *_a, **_k):
        return self

    def pluck(self, *_a, **_k):
        return self

    def run(self, _conn):
        return list(self._rows)


@pytest.fixture()
def simple_iptools(monkeypatch):
    db_stub = types.ModuleType("db")

    class _Conn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    db_stub.vpn_rethink_conn = _Conn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db", db_stub)
    monkeypatch.syspath_prepend(str(SRC_DIR))
    spec = importlib.util.spec_from_file_location(
        "simple_iptools_nullip_under_test", str(SRC_DIR / "simple_iptools.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_desktop_without_an_address_does_not_stop_the_scan(simple_iptools):
    uipt = simple_iptools.UserIpTools.__new__(simple_iptools.UserIpTools)
    added = []

    with patch.object(simple_iptools, "r", _FakeR(STARTED)), patch.object(
        uipt, "desktop_add", side_effect=lambda user, ip: added.append((user, ip))
    ):
        uipt.init_domains_started()

    # The null one is skipped and, decisively, the one after it still runs.
    assert added == [("u3", "10.2.0.9")]


class _FakeUserR(_FakeR):
    """Enough of the driver for the user lookup at the top of desktop_add.

    Without this the lookup raises, desktop_add returns early for a reason that
    has nothing to do with the address, and the case passes on the unfixed code
    too — proving nothing.
    """

    def get(self, _key):
        return self

    def run(self, _conn):
        return {"vpn": {"wireguard": {"Address": "10.1.0.5"}}}


def test_desktop_add_refuses_an_empty_address(simple_iptools):
    uipt = simple_iptools.UserIpTools.__new__(simple_iptools.UserIpTools)
    with patch.object(simple_iptools, "r", _FakeUserR([])), patch.object(
        simple_iptools, "check_output"
    ) as run:
        uipt.desktop_add("u1", None)  # must not raise
    run.assert_not_called()
