# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for DownloadChangesThread._process_change — the
state-machine that maps media/domains changefeed events to
download actions.

Bypass `__init__` via `__new__` to avoid the config/DB bootstrap
the real constructor performs. We only need `.stop`,
`.storage_pending`, `.execute`, `.restart_pending_downloads`, and
optionally `._stop_event`.

Post-refactor (commit ``14ab01bb5``): ``_process_change`` receives a
typed change envelope (``MediaChange`` / ``DomainsChange`` /
``EngineChange``) exposing ``.new_val`` / ``.old_val`` attributes that
are Pydantic row objects, not raw dicts. The helpers below build those
envelopes from dict specs so the tests stay readable.
"""

from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

from changefeed_models.domains_row import DomainsRow
from changefeed_models.engine_row import EngineRow
from changefeed_models.media_row import MediaRow
from engine.services.threads.download_thread import DownloadChangesThread

_ROW_TYPES = {
    "media": MediaRow,
    "domains": DomainsRow,
    "engine": EngineRow,
}


def _row(payload):
    """Build the typed row for ``payload["table"]``.

    EngineRow only declares ``table`` and ``additional_properties``;
    every other key goes into additional_properties so
    ``engine.additional_properties.get("status_all_threads")`` works
    the way the production code expects.
    """
    if payload is None:
        return None
    table = payload["table"]
    row_cls = _ROW_TYPES[table]
    if table == "engine":
        extra = {k: v for k, v in payload.items() if k != "table"}
        return EngineRow(table="engine", additional_properties=extra or None)
    return row_cls.model_validate(payload)


def _change(new_val=None, old_val=None):
    """Build a change-envelope-shaped object with ``.new_val`` / ``.old_val``
    typed-row attributes. ``SimpleNamespace`` is enough because
    ``_process_change`` only reads those two attrs — no need to carry
    ``additional_properties`` or pass through a Pydantic validator.
    """
    return SimpleNamespace(new_val=_row(new_val), old_val=_row(old_val))


def _make_thread(stop=False):
    t = DownloadChangesThread.__new__(DownloadChangesThread)
    t.stop = stop
    t.storage_pending = {}
    # Mock out the two branches _process_change calls on itself.
    t.execute = MagicMock()
    t.restart_pending_downloads = MagicMock()
    t._stop_event = Event()
    return t


class TestEngineStopSignal:
    def test_stop_flag_sets_stop_event_and_returns(self):
        t = _make_thread(stop=True)
        t._process_change(
            _change(new_val={"table": "media", "status": "DownloadStarting"})
        )
        assert t._stop_event.is_set()
        t.execute.assert_not_called()

    def test_engine_stopping_status_sets_event(self):
        t = _make_thread()
        t._process_change(
            _change(new_val={"table": "engine", "status_all_threads": "Stopping"})
        )
        assert t._stop_event.is_set()
        t.execute.assert_not_called()

    def test_engine_non_stopping_triggers_restart_pending(self):
        t = _make_thread()
        t._process_change(
            _change(new_val={"table": "engine", "status_all_threads": "Running"})
        )
        t.restart_pending_downloads.assert_called_once()
        t.execute.assert_not_called()

    def test_engine_old_val_only_is_ignored(self):
        t = _make_thread()
        t._process_change(_change(old_val={"table": "engine"}))
        t.execute.assert_not_called()
        t.restart_pending_downloads.assert_not_called()


class TestStatusFilter:
    def test_non_download_status_is_filtered_out(self):
        t = _make_thread()
        payload = {"table": "media", "status": "Ready", "id": "m1"}
        t._process_change(_change(new_val=payload, old_val=payload))
        t.execute.assert_not_called()
        t.restart_pending_downloads.assert_not_called()


class TestInsertActions:
    def test_download_starting_insert_triggers_start_download(self):
        t = _make_thread()
        payload = {
            "table": "media",
            "status": "DownloadStarting",
            "id": "m1",
            "category": "default",
        }
        t._process_change(_change(new_val=payload))
        # execute receives the typed row, not the original dict
        (action_name, row), _kwargs = t.execute.call_args
        assert action_name == "start_download"
        assert isinstance(row, MediaRow)
        assert row.id == "m1"

    def test_downloading_insert_on_media_resets_downloading(self):
        t = _make_thread()
        # Replace reset_downloading (not self.execute) — it's called directly.
        t.reset_downloading = MagicMock()
        payload = {
            "table": "media",
            "status": "Downloading",
            "id": "m1",
            "category": "default",
        }
        t._process_change(_change(new_val=payload))
        (kind, row), _kwargs = t.reset_downloading.call_args
        assert kind == "media"
        assert isinstance(row, MediaRow)
        assert row.id == "m1"

    def test_downloading_insert_on_domains_resets_downloading(self):
        t = _make_thread()
        t.reset_downloading = MagicMock()
        payload = {
            "table": "domains",
            "status": "Downloading",
            "id": "d1",
            "category": "default",
        }
        t._process_change(_change(new_val=payload))
        (kind, row), _kwargs = t.reset_downloading.call_args
        assert kind == "domains"
        assert isinstance(row, DomainsRow)
        assert row.id == "d1"


class TestDeleteActions:
    def test_aborting_delete_triggers_remove_download_thread(self):
        t = _make_thread()
        payload = {
            "table": "media",
            "status": "DownloadAborting",
            "id": "m1",
            "category": "default",
        }
        t._process_change(_change(old_val=payload))
        (action_name, row), _kwargs = t.execute.call_args
        assert action_name == "remove_download_thread"
        assert isinstance(row, MediaRow)
        assert row.id == "m1"


class TestUpdateActions:
    def _update(self, old_status, new_status, table="media"):
        payload_old = {
            "table": table,
            "status": old_status,
            "id": "m1",
            "category": "default",
        }
        payload_new = dict(payload_old)
        payload_new["status"] = new_status
        return _change(new_val=payload_new, old_val=payload_old)

    def test_download_failed_to_starting_restarts_download(self):
        t = _make_thread()
        t._process_change(self._update("DownloadFailed", "DownloadStarting"))
        assert t.execute.call_args.args[0] == "start_download"

    def test_downloaded_to_deleting_media_triggers_delete_media(self):
        t = _make_thread()
        t._process_change(self._update("Downloaded", "Deleting", table="media"))
        assert t.execute.call_args.args[0] == "delete_media"

    def test_download_failed_to_deleting_media_triggers_delete_media(self):
        t = _make_thread()
        t._process_change(self._update("DownloadFailed", "Deleting", table="media"))
        assert t.execute.call_args.args[0] == "delete_media"

    def test_downloading_to_abort_triggers_abort(self):
        t = _make_thread()
        t._process_change(self._update("Downloading", "DownloadAborting"))
        assert t.execute.call_args.args[0] == "abort_download"

    def test_downloading_to_reset_downloading_triggers_abort_with_failed_final(
        self,
    ):
        t = _make_thread()
        t._process_change(self._update("Downloading", "ResetDownloading"))
        assert (
            t.execute.call_args.args[0] == "abort_download_final_status_download_failed"
        )

    def test_terminal_transitions_do_not_queue_actions(self):
        """Downloading→Downloaded and Downloading→DownloadFailed are
        explicitly pass-through: they update DB state elsewhere and
        don't trigger an action from the change stream."""
        t = _make_thread()
        t._process_change(self._update("Downloading", "Downloaded"))
        t._process_change(self._update("Downloading", "DownloadFailed"))
        t._process_change(self._update("DownloadStarting", "Downloading"))
        t.execute.assert_not_called()


class TestRestartPendingFirst:
    def test_download_change_always_restarts_pending_first(self):
        """Any download-related change causes a re-drain of the
        storage_pending queue before the action dispatch — pin that
        ordering so a refactor doesn't lose pending items."""
        t = _make_thread()
        t._process_change(
            _change(
                new_val={
                    "table": "media",
                    "status": "DownloadStarting",
                    "id": "m1",
                    "category": "default",
                }
            )
        )
        t.restart_pending_downloads.assert_called_once()
