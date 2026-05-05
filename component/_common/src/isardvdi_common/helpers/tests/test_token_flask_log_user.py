# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression test for ``TokenFlask.log_user``.

Background: the previous implementation called ``gevent.spawn(LogsUsers,
payload)``. ``gevent.spawn`` enqueues a callback on the libev Hub, which
fires only when the running greenlet yields — and yields only happen
when stdlib socket / select / time calls are monkey-patched into
cooperative versions. Of the three Flask services that import
``TokenFlask``:

  * ``scheduler`` calls ``gevent.monkey.patch_all()`` at process startup
    — Hub runs, greenlet fires, audit row is written.
  * ``webapp`` runs on waitress (stdlib threads + ``select``) and never
    monkey-patches — Hub never runs, greenlet enqueued forever, audit
    row silently never written.
  * ``notifier`` is same as webapp.

That meant every authenticated request through webapp / notifier
silently dropped its ``logs_users`` row. No exception, no warning, no
test failure — invisible until someone audited the table.

The fix replaces ``gevent.spawn`` with a daemon ``threading.Thread``,
which runs on a real OS thread under all three runtimes. This test
verifies the new behaviour by faking ``LogsUsers`` and asserting it
actually executes (in any reasonable wall-clock window) without any
``monkey.patch_all`` having been called.
"""

import logging
import sys
import threading
import time
import types
from unittest.mock import patch

import pytest


@pytest.fixture
def token_flask_module():
    """Import the module under test once per test, fresh.

    ``token_flask`` imports ``isardvdi_common.helpers.api_exceptions_flask``
    which in turn needs one of ``webapp`` / ``scheduler`` / ``notifier``
    to be importable so it can bind ``app.logger``. None of those Flask
    service packages are on the Python path inside the apiv4 (or any
    pure-``_common``) test environment, so we inject a minimal stub
    matching the contract the module reads — a ``logger`` attribute and
    an ``errorhandler`` decorator. This lets the test live alongside the
    other ``_common`` unit tests without forcing the suite into a
    specific service container.
    """
    if "webapp" not in sys.modules:
        webapp_stub = types.ModuleType("webapp")
        webapp_stub.app = types.SimpleNamespace(
            logger=logging.getLogger("test-stub"),
            errorhandler=lambda exc_type: (lambda fn: fn),
        )
        sys.modules["webapp"] = webapp_stub

    import isardvdi_common.helpers.token_flask as mod

    return mod


def test_log_user_actually_runs_logsusers_target(token_flask_module):
    """``log_user(payload)`` must execute ``LogsUsers(payload)`` on a
    real thread, observable from the calling thread within a short
    timeout. The previous gevent-based implementation would silently
    enqueue and never run under waitress/asyncio — this test catches
    that regression.
    """
    invocations: list = []
    invoked_event = threading.Event()

    def fake_logsusers(payload):
        invocations.append(payload)
        invoked_event.set()

    payload = {"user_id": "test-user-1", "action": "login"}

    with patch.object(token_flask_module, "LogsUsers", side_effect=fake_logsusers):
        token_flask_module.TokenFlask.log_user(payload)

        # Bounded wait — daemon threads under stdlib runtime should
        # start within ms. 2s is generous; if this test exceeds, the
        # implementation regressed back to a Hub-based primitive.
        assert invoked_event.wait(timeout=2.0), (
            "LogsUsers was never invoked. The previous gevent.spawn "
            "implementation produced this exact failure mode under "
            "waitress (no monkey.patch_all): the spawn callback was "
            "enqueued on the libev Hub but the Hub never ran, so the "
            "audit-log write silently disappeared."
        )

    assert invocations == [payload], "Target was called with wrong args"


def test_log_user_does_not_block_caller(token_flask_module):
    """``log_user`` is fire-and-forget — the calling request handler
    must not wait for ``LogsUsers`` to finish (which can be slow if
    isard-db is unreachable: ``LogsUsers.__init__`` opens its own
    rdb connection).
    """
    started = threading.Event()
    blocking_finish = threading.Event()

    def slow_logsusers(payload):
        started.set()
        # Simulate a slow rdb write that the handler must NOT wait for
        blocking_finish.wait(timeout=5.0)

    with patch.object(token_flask_module, "LogsUsers", side_effect=slow_logsusers):
        t0 = time.monotonic()
        token_flask_module.TokenFlask.log_user({"user_id": "u"})
        elapsed = time.monotonic() - t0

        # log_user must return immediately even though the target is
        # still running. 100ms is a generous ceiling; threading.Thread
        # start() itself is sub-millisecond.
        assert (
            elapsed < 0.1
        ), f"log_user blocked the caller for {elapsed:.3f}s — must be fire-and-forget"

        # Prove the target actually started (so we know the test
        # actually exercised the spawn path, not a dead branch)
        assert started.wait(
            timeout=2.0
        ), "Target thread never started — the spawn primitive is broken"

        # Let the slow target finish so it doesn't leak across tests
        blocking_finish.set()


def test_log_user_swallows_thread_start_failures(token_flask_module, caplog):
    """``Thread.start()`` failures (e.g. thread-table exhaustion under
    DoS) must not propagate to the request handler. The previous
    gevent-based code had the same try/except contract; preserve it.

    A side-effect-raising Thread is hard to fake without monkeypatching
    ``threading.Thread`` itself, which would corrupt other tests'
    bookkeeping. Patch the module-local reference instead.
    """

    class ExplodingThread:
        def __init__(self, *a, **kw):
            pass

        def start(self):
            raise RuntimeError("can't create thread")

    with patch.object(token_flask_module.threading, "Thread", ExplodingThread):
        with caplog.at_level(logging.WARNING):
            # Must not raise — fire-and-forget contract requires that
            # audit-log failures never break the auth flow.
            token_flask_module.TokenFlask.log_user({"user_id": "u"})

    # And the failure should at least be logged so a silent-audit-path
    # bug is loud enough to grep for. ``caplog.text`` is the full
    # captured log output regardless of which formatter ran.
    assert "WARNING" in caplog.text and "LogsUsers" in caplog.text, (
        "Thread.start() failure should produce a WARNING log line "
        f"mentioning LogsUsers — got: {caplog.text!r}"
    )


def test_module_does_not_import_gevent(token_flask_module):
    """Regression guard for the actual fix: ``token_flask`` must not
    import ``gevent`` anywhere or call ``gevent.spawn``. The whole
    point of the migration was to remove the silent-data-loss path
    that gevent.spawn produced under non-monkey-patched runtimes.

    Uses ``ast`` to walk the module's actual import statements + call
    expressions, ignoring docstrings / comments where the legacy
    pattern is referenced for historical context.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(token_flask_module))

    for node in ast.walk(tree):
        # No `import gevent` or `from gevent import …`
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not (
                    alias.name == "gevent" or alias.name.startswith("gevent.")
                ), (
                    f"token_flask must not import gevent (line {node.lineno}: "
                    f"{ast.dump(node)})"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in (
                "gevent",
                "gevent.monkey",
            ), f"token_flask must not import from gevent (line {node.lineno})"

        # No `gevent.spawn(...)` calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            full = ast.unparse(node.func)
            assert "gevent" not in full, (
                f"token_flask must not call gevent (line {node.lineno}: "
                f"got {full!r})"
            )
