# SPDX-License-Identifier: AGPL-3.0-or-later

"""Abort and retry decide from a row the settle path writes at the same moment."""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.media import MediaService


class _Media:
    store = {}
    read_as = {}

    def __init__(self, media_id):
        object.__setattr__(self, "id", media_id)
        object.__setattr__(self, "user", "u1")
        object.__setattr__(self, "url-web", "https://example.com/x.iso")
        object.__setattr__(self, "url-isard", False)

    @property
    def status(self):
        return self.read_as.get(self.id, self.store.get(self.id, {}).get("status"))

    @classmethod
    def exists(cls, media_id):
        return media_id in cls.store

    @classmethod
    def update_document_if(cls, doc_id, update_data, *, field, values, validate=True):
        row = cls.store.get(doc_id)
        if row is None or row.get(field) not in values:
            return False
        row.update(update_data)
        return True

    def __setattr__(self, name, value):
        self.store[self.id][name] = value


@pytest.fixture
def rows(monkeypatch):
    _Media.store = {}
    _Media.read_as = {}
    monkeypatch.setattr("api.services.media.RethinkMedia", _Media)
    return _Media


@pytest.fixture
def no_task(monkeypatch):
    """No chain is pending, so abort takes its settle-it-here branch."""
    monkeypatch.setattr("api.services.media.current_task_id", lambda *a, **k: None)


class TestAbort:
    def test_an_abort_does_not_stamp_a_row_the_chain_already_settled(
        self, rows, no_task
    ):
        """The settle wrote ``Downloaded`` between the read and the write."""
        rows.read_as["m1"] = "Downloading"
        rows.store["m1"] = {"status": "Downloaded"}

        with pytest.raises(Error) as exc:
            MediaService.abort_media_download("m1")

        assert exc.value.error["error"] == "bad_request"
        assert rows.store["m1"]["status"] == "Downloaded"

    def test_an_abort_with_no_pending_task_does_not_undo_a_settle(
        self, rows, monkeypatch
    ):
        """The chain settled between the aborting flag and the fallback write."""
        rows.store["m1"] = {"status": "Downloading"}

        def _settled_meanwhile(*_a, **_k):
            rows.store["m1"]["status"] = "Downloaded"
            return None

        monkeypatch.setattr("api.services.media.current_task_id", _settled_meanwhile)

        MediaService.abort_media_download("m1")

        assert rows.store["m1"]["status"] == "Downloaded"

    def test_an_abort_of_a_running_download_still_settles_it(self, rows, no_task):
        """The control: nothing else touched the row."""
        rows.store["m1"] = {"status": "Downloading"}

        MediaService.abort_media_download("m1")

        assert rows.store["m1"]["status"] == "DownloadFailed"

    def test_an_unknown_media_is_not_found(self, rows):
        with pytest.raises(Error) as exc:
            MediaService.abort_media_download("ghost")
        assert exc.value.error["error"] == "not_found"


class TestStart:
    def test_a_second_retry_does_not_enqueue_a_second_chain(self, rows):
        """Two retries of one media would run two curls into the same path."""
        rows.read_as["m1"] = "DownloadFailed"
        rows.store["m1"] = {"status": "DownloadStarting"}

        with patch.object(_Media, "enqueue_download_chain", create=True) as enqueue:
            with pytest.raises(Error) as exc:
                MediaService.start_media_download("m1")

        assert exc.value.error["error"] == "bad_request"
        enqueue.assert_not_called()
        assert rows.store["m1"]["status"] == "DownloadStarting"

    def test_a_retry_of_a_failed_download_still_starts(self, rows):
        """The control."""
        rows.store["m1"] = {"status": "DownloadFailed"}

        with patch.object(_Media, "enqueue_download_chain", create=True) as enqueue:
            MediaService.start_media_download("m1")

        assert rows.store["m1"]["status"] == "DownloadStarting"
        assert rows.store["m1"]["progress"]["received"] == "0"
        enqueue.assert_called_once()
