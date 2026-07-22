"""Unit tests for the slow-query / failed-query observer wired into
``_common.connections.rethink_shared_connection._connection_factory``
(P2.1 of the rethinkdb fork modernization plan).

The observer is fired by the rethinkdb driver for every query a
pooled connection runs; we want to see structured log lines for
queries that crossed the slow threshold or raised, and silence
otherwise.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def observer(monkeypatch):
    """Return the on_end callback at the threshold the test sets."""
    # Force the threshold deterministic regardless of the current env.
    monkeypatch.setenv("RETHINKDB_SLOW_QUERY_MS", "500")
    # Re-import the module so the cached _SLOW_QUERY_S picks up the env.
    import importlib

    from isardvdi_common.connections import rethink_shared_connection as mod

    importlib.reload(mod)
    return mod._query_observer_on_end


def _fake_query(term_repr: str = "r.table('users').get('u-1')"):
    """Minimal Query stand-in: only ``term`` and ``type`` are read by
    ``_summarize_query``."""
    term = MagicMock()
    term.__repr__ = lambda self: term_repr
    return SimpleNamespace(term=term, type=1)


class TestSlowQueryThreshold:
    def test_fast_query_is_silent(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 0.05, None)  # 50 ms
        assert caplog.records == [], "fast queries must not log"

    def test_at_threshold_logs(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 0.5, None)  # exactly 500 ms
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.message == "rdb_query_slow"
        # ``extra`` dict landed on the record as attributes
        assert rec.duration_ms == 500.0
        assert "table('users')" in rec.query

    def test_slow_query_logs(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 1.234, None)  # 1234 ms
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.message == "rdb_query_slow"
        assert rec.duration_ms == 1234.0


class TestFailedQuery:
    def test_failed_fast_query_logs(self, observer, caplog):
        """Failures always log — even sub-threshold ones — because
        durability of the error trail matters more than log volume."""
        caplog.set_level(logging.WARNING, logger="rdb.query")
        err = ValueError("connection lost mid-query")
        observer(_fake_query(), 0.01, err)  # 10 ms; below threshold
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.message == "rdb_query_failed"
        assert rec.error_type == "ValueError"
        assert "connection lost" in rec.error_msg
        assert rec.duration_ms == 10.0

    def test_error_msg_truncated(self, observer, caplog):
        """Bound the error message to 200 chars so a runaway exception
        (e.g. a 50KB rdb error blob) doesn't blow up Loki ingestion."""
        caplog.set_level(logging.WARNING, logger="rdb.query")
        err = RuntimeError("x" * 500)
        observer(_fake_query(), 0.001, err)
        assert len(caplog.records) == 1
        assert len(caplog.records[0].error_msg) == 200


class TestQuerySummarizer:
    def test_summary_truncated_to_200_chars(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query("r.table('x')." * 100), 1.0, None)
        rec = caplog.records[0]
        assert len(rec.query) == 200

    def test_summary_handles_unrepresentable_term(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        bad_term = MagicMock()

        def bad_repr(_self):
            raise RuntimeError("repr broke")

        bad_term.__repr__ = bad_repr
        query = SimpleNamespace(term=bad_term, type=1)
        # Must not raise — the observer wraps the repr() call.
        observer(query, 1.0, None)
        rec = caplog.records[0]
        assert rec.query == "<unrepresentable>"

    def test_summary_handles_none_term(self, observer, caplog):
        caplog.set_level(logging.WARNING, logger="rdb.query")
        query = SimpleNamespace(term=None, type=42)
        observer(query, 1.0, None)
        rec = caplog.records[0]
        assert rec.query == "<query type=42>"


class TestObserverWiringContract:
    """Pin the contract that ``_connection_factory`` registers exactly
    one ``on_end`` observer per pooled connection. If a refactor
    silently drops the registration the route layer's slow-query
    visibility goes dark, so this test guards against that.
    """

    def test_connection_factory_registers_observer(self, monkeypatch):
        from isardvdi_common.connections import rethink_shared_connection as mod

        captured = {"observers": []}

        def fake_connect(**_kwargs):
            class FakeConn:
                def add_query_observer(self, on_start=None, on_end=None):
                    captured["observers"].append((on_start, on_end))
                    return (on_start, on_end)

            return FakeConn()

        monkeypatch.setattr(mod.r, "connect", fake_connect)

        mod._connection_factory()

        assert (
            len(captured["observers"]) == 1
        ), "exactly one observer must be registered per pooled connection"
        on_start, on_end = captured["observers"][0]
        assert on_start is None, "we don't need a start hook"
        assert on_end is mod._query_observer_on_end, (
            "the registered hook must be the module-level callable so "
            "tests can drive it directly without standing up a real pool"
        )


class TestPoolStatsEnrichment:
    """Pin that every emitted slow/failed log line carries the pool's
    snapshot (size/in_use/idle/max_size). Without it, "slow" and
    "saturated" look identical in Loki and operators can't tell
    whether to raise the pool size or hunt the slow query.
    """

    def _stub_pool(self, monkeypatch, **stats):
        from isardvdi_common.connections import rethink_shared_connection as mod

        class _StubPool:
            size = stats.get("size", 4)
            in_use = stats.get("in_use", 3)
            idle = stats.get("idle", 1)
            max_size = stats.get("max_size", 10)

        monkeypatch.setattr(mod, "_pool", _StubPool())

    def test_slow_log_carries_pool_stats(self, observer, caplog, monkeypatch):
        self._stub_pool(monkeypatch, size=8, in_use=7, idle=1, max_size=10)
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 1.0, None)
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.pool_size == 8
        assert rec.pool_in_use == 7
        assert rec.pool_idle == 1
        assert rec.pool_max_size == 10

    def test_failed_log_carries_pool_stats(self, observer, caplog, monkeypatch):
        self._stub_pool(monkeypatch, size=4, in_use=4, idle=0, max_size=4)
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 0.01, RuntimeError("boom"))
        rec = caplog.records[0]
        assert rec.pool_in_use == 4
        assert rec.pool_idle == 0

    def test_no_pool_omits_stats(self, observer, caplog, monkeypatch):
        """Tests / dedicated-connection callers may run before the
        pool is initialized; the observer must NOT raise and must
        omit the pool fields rather than emit ``None``s."""
        from isardvdi_common.connections import rethink_shared_connection as mod

        monkeypatch.setattr(mod, "_pool", None)
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 1.0, None)
        rec = caplog.records[0]
        assert not hasattr(rec, "pool_size")

    def test_pool_property_failure_does_not_break_observer(
        self, observer, caplog, monkeypatch
    ):
        """Pool properties raise transiently mid-close() — the observer
        must drop the enrichment rather than propagate, otherwise a
        single log line could break the network thread's query loop."""
        from isardvdi_common.connections import rethink_shared_connection as mod

        class _BadPool:
            @property
            def size(self):
                raise RuntimeError("closing")

            @property
            def in_use(self):
                raise RuntimeError("closing")

            @property
            def idle(self):
                raise RuntimeError("closing")

            @property
            def max_size(self):
                raise RuntimeError("closing")

        monkeypatch.setattr(mod, "_pool", _BadPool())
        caplog.set_level(logging.WARNING, logger="rdb.query")
        observer(_fake_query(), 1.0, None)
        # Still a log record, just without pool fields.
        rec = caplog.records[0]
        assert not hasattr(rec, "pool_size")
