"""What the domain write helpers do with the result RethinkDB hands back."""

import importlib.util as _ilu
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

from tests.helpers import ENGINE_SRC

# set the level on the existing ``logs``: replacing the module breaks sibling tests
import engine.services.log as _engine_log

try:
    _engine_log.logs.changes.handlers[0].level = 20
except Exception:
    pass

# load from file under a stub package so db/__init__ and its connections never run
_saved = {
    _m: _sys.modules.get(_m)
    for _m in (
        "engine.services.db",
        "engine.services.db.db",
        "engine.services.db.domains",
        "rethinkdb",
    )
}
_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = []
for _name in (
    "close_rethink_connection",
    "create_list_buffer_history_domain",
    "new_rethink_connection",
    "rethink_conn",
):
    setattr(_pkg, _name, _MagicMock())
_sys.modules["engine.services.db"] = _pkg
# domains.py also imports engine.services.db.db, which connects at import time.
_db = _types.ModuleType("engine.services.db.db")
_db.close_rethink_connection = _MagicMock()
_db.new_rethink_connection = _MagicMock()
_sys.modules["engine.services.db.db"] = _db
_sys.modules.pop("rethinkdb", None)

_spec = _ilu.spec_from_file_location(
    "engine.services.db.domains",
    str(ENGINE_SRC / "services" / "db" / "domains.py"),
)
mod = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

for _m, _prev in _saved.items():
    if _prev is None:
        _sys.modules.pop(_m, None)
    else:
        _sys.modules[_m] = _prev

from contextlib import contextmanager  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

DOMAIN_ID = "desktop-that-was-deleted"

# What the server returns for a write aimed at a row that is gone.
MISSING_ROW_RESULT = {
    "changes": [],
    "deleted": 0,
    "errors": 1,
    "first_error": "Cannot perform without on a non-object non-sequence `null`.",
    "inserted": 0,
    "replaced": 0,
    "skipped": 0,
    "unchanged": 0,
}


@pytest.fixture
def stub(monkeypatch):
    """Replace the driver and the connection so the helpers run end to end
    against a canned query result, and capture what gets logged."""

    @contextmanager
    def _conn():
        yield MagicMock(name="connection")

    monkeypatch.setattr(mod, "rethink_conn", _conn)

    logs = MagicMock()
    monkeypatch.setattr(mod, "logs", logs)

    driver = MagicMock()
    # ``domains.py`` catches ``r.ReqlNonExistenceError``, so the stub has to
    # keep the real class there or the except clause is not a valid handler.
    driver.ReqlNonExistenceError = mod.ReqlNonExistenceError
    monkeypatch.setattr(mod, "r", driver)

    def _returns(result):
        driver.table.return_value.get.return_value.replace.return_value.run.return_value = (
            result
        )
        driver.table.return_value.get.return_value.update.return_value.run.return_value = (
            result
        )

    return {"logs": logs, "driver": driver, "returns": _returns}


def _logged(logs):
    """Every message passed to any level of ``logs.main``, flattened."""
    out = []
    for level in ("error", "warning", "info", "debug"):
        for call in getattr(logs.main, level).call_args_list:
            out.append(" ".join(str(a) for a in call.args))
    return " | ".join(out)


def test_stopped_write_to_missing_row_is_reported(stub):
    """A vanished row in the Stopped replace comes back as errors:1 and must be logged."""
    stub["returns"](MISSING_ROW_RESULT)

    mod.update_domain_status(status="Stopped", id_domain=DOMAIN_ID)

    assert stub["logs"].main.error.called, "an errors:1 result was not logged"
    assert DOMAIN_ID in _logged(stub["logs"])


def test_successful_stopped_write_is_not_reported_as_an_error(stub):
    """A write that lands must stay quiet on the error channel."""
    stub["returns"]({"errors": 0, "replaced": 1, "skipped": 0, "changes": []})

    mod.update_domain_status(status="Stopped", id_domain=DOMAIN_ID)

    assert not stub["logs"].main.error.called


def test_remove_viewer_values_does_not_claim_success_on_error(stub):
    """It returned True and logged 'Viewer values removed' for a write that
    errored, because it only inspected replaced/unchanged."""
    stub["returns"](MISSING_ROW_RESULT)

    assert mod.remove_domain_viewer_values(DOMAIN_ID) is False
    assert "Viewer values removed" not in _logged(stub["logs"])


def test_remove_viewer_values_still_reports_a_real_removal(stub):
    stub["returns"]({"errors": 0, "replaced": 1, "unchanged": 0})

    assert mod.remove_domain_viewer_values(DOMAIN_ID) is True


def test_remove_viewer_values_still_false_when_not_stopped(stub):
    """A running domain leaves the document untouched: unchanged, no error."""
    stub["returns"]({"errors": 0, "replaced": 0, "unchanged": 1})

    assert mod.remove_domain_viewer_values(DOMAIN_ID) is False


def test_keep_hyp_id_on_missing_row_still_returns_false(stub):
    """Non-regression: the keep_hyp_id pluck on a null row still raises."""
    stub[
        "driver"
    ].table.return_value.get.return_value.pluck.return_value.run.side_effect = mod.ReqlNonExistenceError(
        "Cannot perform pluck on a non-object non-sequence `null`."
    )

    assert (
        mod.update_domain_status(
            status="Started", id_domain=DOMAIN_ID, keep_hyp_id=True
        )
        is False
    )
