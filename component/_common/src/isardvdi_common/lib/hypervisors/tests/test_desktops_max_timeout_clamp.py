# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the one-year clamp on ``HypervisorsProcessed.get_desktops_max_timeout``."""

from unittest.mock import MagicMock

import pytest


class _Chain:
    """Chainable rethink-query stub; ``.run(...)`` yields the stored value."""

    def __init__(self, value):
        self._value = value

    def __getattr__(self, name):
        if name == "run":
            return lambda *a, **k: self._value
        return lambda *a, **k: self

    def __getitem__(self, _key):
        return self


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    def _set_stored(value):
        fake_r = MagicMock(name="r")
        fake_r.table = lambda name: _Chain(value)
        monkeypatch.setattr(mod, "r", fake_r)
        # The result is memoized — clear so each case recomputes.
        mod.HypervisorsProcessed.clear_get_desktops_max_timeout_cache()

    return {"mod": mod, "set_stored": _set_stored}


def test_clamps_value_above_one_year(stub_rdb):
    stub_rdb["set_stored"](999999)
    assert stub_rdb["mod"].HypervisorsProcessed.get_desktops_max_timeout() == 525600


def test_passes_through_in_range_value(stub_rdb):
    stub_rdb["set_stored"](720)
    assert stub_rdb["mod"].HypervisorsProcessed.get_desktops_max_timeout() == 720


def test_passes_through_exact_one_year(stub_rdb):
    stub_rdb["set_stored"](525600)
    assert stub_rdb["mod"].HypervisorsProcessed.get_desktops_max_timeout() == 525600
