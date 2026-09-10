# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures for the ``isardvdi_vpn`` unit tests.

The modules under test are imported normally: ``wgadmin``'s runtime loop and
the monitor threads live inside ``main()``, guarded by ``if __name__ ==
"__main__"``, so importing the package has no side effects.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest
from isardvdi_vpn import simple_iptools as _simple_iptools
from isardvdi_vpn import wgtools


@pytest.fixture
def wgtools_hyper():
    """A Wg instance with table='hypervisors' and no __init__ side effects."""
    Wg = wgtools.Wg
    instance = Wg.__new__(Wg)
    instance.table = "hypervisors"
    instance.interface = "wg0"
    instance.uipt = MagicMock()
    return instance


@pytest.fixture
def wgtools_module():
    return wgtools


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

    class _FakeVpnRethinkConn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(_simple_iptools, "vpn_rethink_conn", _FakeVpnRethinkConn)
    return _simple_iptools
