# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stubs needed before importing wgadmin.

wgadmin.py has several import-time side effects that make it unsafe to import
directly in a test process:

- ``wg_monitor.start_monitoring_vpn_status()`` spawns a background thread.
- ``from wgtools import Wg`` pulls in ``simple_iptools`` → ``iptc`` (a native
  library not available in the test environment).
- After the function definitions, the module enters a ``while True`` loop that
  connects to RethinkDB and spins up a ``RedisStreamConsumer``.

The fixtures here stub those dependencies and expose the real
``_process_vpn_change`` function from the module so dispatch tests can
exercise it without touching the loop body.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


class _BreakWhileLoop(BaseException):
    """Escape hatch to abort wgadmin's module-level ``while True`` loop.

    wgadmin catches ``Exception`` inside the loop and sleeps, so we inherit
    from ``BaseException`` instead to escape unambiguously.
    """


def _install_stubs() -> None:
    # Prevent start_monitoring_vpn_status() from spawning its thread.
    wg_monitor = types.ModuleType("wg_monitor")
    wg_monitor.start_monitoring_vpn_status = lambda: None  # type: ignore[attr-defined]
    sys.modules["wg_monitor"] = wg_monitor

    # wgadmin calls ``tunnel_monitor.start()`` at import time, which spawns a
    # daemon polling thread; stub it out like wg_monitor above.
    tunnel_monitor = types.ModuleType("tunnel_monitor")
    tunnel_monitor.start = lambda: None  # type: ignore[attr-defined]
    sys.modules["tunnel_monitor"] = tunnel_monitor

    # wgtools pulls in iptc via simple_iptools; stub it with a dummy Wg class.
    wgtools = types.ModuleType("wgtools")

    class _DummyWg:
        def __init__(self, *args, **kwargs) -> None:
            pass

    wgtools.Wg = _DummyWg  # type: ignore[attr-defined]
    sys.modules["wgtools"] = wgtools

    # Environment vars required by the module-level loop (even though we abort it).
    os.environ.setdefault("WG_HYPERS_NET", "10.0.0.0/24")
    os.environ.setdefault("WG_HYPERS_PORT", "4443")
    os.environ.setdefault("WG_USERS_NET", "10.1.0.0/24")
    os.environ.setdefault("WG_USERS_PORT", "4444")
    os.environ.setdefault("WG_GUESTS_NETS", "10.2.0.0/24")

    # Neutralise RethinkDB so the module-level rdb queries do not try to
    # reach a real server before the while-loop aborts.
    import rethinkdb as _rdb

    class _FakeConn:
        def repl(self):
            return self

    class _FakeQuery:
        def pluck(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def run(self, *args, **kwargs):
            return []

    class _FakeR:
        def connect(self, *args, **kwargs):
            return _FakeConn()

        def table(self, *args, **kwargs):
            return _FakeQuery()

    _rdb.RethinkDB = lambda: _FakeR()  # type: ignore[attr-defined]

    # Stub the new pooled-connection helper so tests don't hit the real
    # ``isardvdi_common`` pool (which would try to open an rdb socket).
    db_stub = types.ModuleType("db")

    class _FakePoolConn:
        """Yielded value from ``vpn_rethink_conn()`` in tests."""

    class _FakeVpnRethinkConn:
        def __enter__(self):
            return _FakePoolConn()

        def __exit__(self, *args):
            return False

    db_stub.vpn_rethink_conn = _FakeVpnRethinkConn  # type: ignore[attr-defined]
    sys.modules["db"] = db_stub

    # Force the while-True loop to exit via a BaseException subclass that the
    # except-Exception clause will not catch.
    import isardvdi_common.redis_stream as _rs

    def _abort(*args, **kwargs):
        raise _BreakWhileLoop

    _rs.RedisStreamConsumer = _abort  # type: ignore[attr-defined]


def _load_wgadmin():
    _install_stubs()
    spec = importlib.util.spec_from_file_location(
        "wgadmin", str(SRC_DIR / "wgadmin.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["wgadmin"] = module
    try:
        spec.loader.exec_module(module)
    except _BreakWhileLoop:
        # Expected: the while-loop was aborted after _process_vpn_change was defined.
        pass
    return module


@pytest.fixture(scope="session")
def wgadmin_module():
    """Return the wgadmin module with its while-loop safely aborted."""
    if "wgadmin" in sys.modules and hasattr(
        sys.modules["wgadmin"], "_process_vpn_change"
    ):
        return sys.modules["wgadmin"]
    return _load_wgadmin()


def _load_wgtools():
    """Import the real wgtools module, stubbing iptc and simple_iptools.

    wgtools pulls in ``simple_iptools`` which imports the native ``iptc``
    library. We only need the module-level symbols and the ``Wg`` class for
    unit tests of ``up_peer``/``down_peer``; the ``__init__`` side effects
    are avoided by constructing instances via ``Wg.__new__``.
    """
    # Stub iptc before simple_iptools tries to import it.
    if "iptc" not in sys.modules:
        iptc_stub = types.ModuleType("iptc")
        sys.modules["iptc"] = iptc_stub

    # Replace simple_iptools with a minimal stub exposing UserIpTools.
    simple_iptools_stub = types.ModuleType("simple_iptools")

    class _DummyUserIpTools:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def remove_matching_rules(self, *args, **kwargs) -> None:
            pass

    simple_iptools_stub.UserIpTools = _DummyUserIpTools  # type: ignore[attr-defined]
    sys.modules["simple_iptools"] = simple_iptools_stub

    # Stub changefeed_models.{hypervisors_row,users_row} — wgtools only
    # imports the Row classes for model_validate(); we pass dicts, so a
    # stub class is sufficient.
    changefeed_models_pkg = types.ModuleType("changefeed_models")
    changefeed_models_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["changefeed_models"] = changefeed_models_pkg

    hypers_mod = types.ModuleType("changefeed_models.hypervisors_row")

    class _StubRow:
        @classmethod
        def model_validate(cls, data):
            return data

    hypers_mod.HypervisorsRow = _StubRow  # type: ignore[attr-defined]
    sys.modules["changefeed_models.hypervisors_row"] = hypers_mod

    users_mod = types.ModuleType("changefeed_models.users_row")
    users_mod.UsersRow = _StubRow  # type: ignore[attr-defined]
    sys.modules["changefeed_models.users_row"] = users_mod

    # Add SRC_DIR to sys.path for any other relative imports.
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    # Remove any pre-existing stubbed wgtools (wgadmin fixture installs one).
    if (
        "wgtools" in sys.modules
        and not hasattr(sys.modules["wgtools"], "Wg")
        or (
            "wgtools" in sys.modules
            and getattr(sys.modules["wgtools"].Wg, "__module__", "") != "wgtools"
        )
    ):
        del sys.modules["wgtools"]

    if "wgtools" in sys.modules:
        return sys.modules["wgtools"]

    spec = importlib.util.spec_from_file_location(
        "wgtools", str(SRC_DIR / "wgtools.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["wgtools"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def wgtools_module():
    """Return the real wgtools module with iptc/simple_iptools stubbed."""
    return _load_wgtools()


@pytest.fixture
def wgtools_hyper(wgtools_module):
    """A Wg instance with table='hypervisors' and no __init__ side effects."""
    from unittest.mock import MagicMock

    Wg = wgtools_module.Wg
    instance = Wg.__new__(Wg)
    instance.table = "hypervisors"
    instance.interface = "wg0"
    instance.uipt = MagicMock()
    return instance


class FakeIptables:
    """A FORWARD chain that answers like netfilter does, as ``check_output``.

    The suites mock ``check_output`` to a bare Mock, which pins the commands
    emitted and their order but says nothing about the chain they leave. This
    keeps the rules, so a test can assert on the result instead.
    """

    OPS = ("-A", "-I", "-D", "-C", "-F", "-P", "-S")

    def __init__(self):
        self.forward = []

    def __call__(self, argv, *args, **kwargs):
        argv = list(argv)
        op = next((token for token in argv if token in self.OPS), None)
        rule = tuple(argv[argv.index(op) + 2 :]) if op else ()

        if op == "-A":
            self.forward.append(rule)
        elif op == "-I":
            self.forward.insert(0, rule)
        elif op == "-D":
            if rule not in self.forward:
                raise subprocess.CalledProcessError(1, argv)
            self.forward.remove(rule)
        elif op == "-C":
            if rule not in self.forward:
                raise subprocess.CalledProcessError(1, argv)
        elif op == "-F":
            self.forward.clear()
        elif op == "-S":
            return "\n".join(
                ["-P FORWARD DROP"]
                + ["-A FORWARD " + " ".join(r) for r in self.forward]
            )
        return ""

    def seed(self, *rule):
        """Put a rule in the chain without going through the code under test."""
        self.forward.append(tuple(rule))

    def count(self, *rule):
        return self.forward.count(tuple(rule))


@pytest.fixture
def fake_iptables():
    return FakeIptables()


@pytest.fixture
def simple_iptools(monkeypatch):
    """The real ``simple_iptools`` module, with only its database stubbed."""
    db_stub = types.ModuleType("db")

    class _FakeVpnRethinkConn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    db_stub.vpn_rethink_conn = _FakeVpnRethinkConn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db", db_stub)
    monkeypatch.syspath_prepend(str(SRC_DIR))

    spec = importlib.util.spec_from_file_location(
        "simple_iptools_under_test", str(SRC_DIR / "simple_iptools.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
