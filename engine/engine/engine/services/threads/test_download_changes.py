"""Happy-path test for `DownloadChangesThread.start_download` URL resolution.

Verifies the consumer correctly reads `url_web` off the Pydantic `MediaRow`
envelope and passes it as the first positional arg to `DownloadThread`.
"""

import shlex
from os.path import dirname
from unittest.mock import MagicMock, patch

from changefeed_models.media_row import MediaRow
from engine.services.threads.download_thread import (
    DownloadChangesThread,
    DownloadThread,
)


def _thread() -> DownloadChangesThread:
    t = DownloadChangesThread.__new__(DownloadChangesThread)
    t.manager = MagicMock()
    t.threads_disk_operations = MagicMock()
    t.download_threads = {}
    t.finalished_threads = []
    t.url_resources = "https://resources.example/storage"
    t.url_code = ""
    # `start_download` calls `self.get_file_path` first; stub it to a fixed
    # 4-tuple matching the production signature.
    t.get_file_path = MagicMock(  # type: ignore[method-assign]
        return_value=("/tmp/x.iso", "default", "media", "pool-1")
    )
    return t


def test_start_download_resolves_url_to_url_web():
    t = _thread()
    media = MediaRow(
        id="m1",
        table="media",
        url_web="https://example.com/x.iso",
        kind="iso",
        category="default",
    )

    with patch(
        "engine.services.threads.download_thread.DownloadThread"
    ) as mock_download_thread:
        # Prevent `.daemon = True; .start()` from doing anything observable.
        mock_download_thread.return_value = MagicMock()

        t.start_download(media)

    mock_download_thread.assert_called_once()
    args = mock_download_thread.call_args.args
    # `url` is the first positional argument (download_thread.py:649-662).
    assert args[0] == "https://example.com/x.iso"
    # `new_file_path` is second.
    assert args[1] == "/tmp/x.iso"
    # `table` is fourth.
    assert args[3] == "media"
    # `id_down` is fifth.
    assert args[4] == "m1"


def test_process_change_download_failed_to_deleting_passes_model():
    """Regression: DownloadFailed -> Deleting must call execute() with the
    model, not its id. Previously line 868 passed ``new_val.id`` (a str),
    causing AttributeError on dict_changes.category inside execute()."""
    thread = _thread()
    thread.stop = False
    thread.storage_pending = {}
    thread.restart_pending_downloads = MagicMock()  # type: ignore[method-assign]

    old_val = MagicMock(status="DownloadFailed", table="media", id="m-1")
    new_val = MagicMock(status="Deleting", table="media", id="m-1", category="cat-a")
    change = MagicMock(old_val=old_val, new_val=new_val)

    with patch.object(thread, "execute") as mock_execute:
        thread._process_change(change)

    mock_execute.assert_called_once_with("delete_media", new_val)


def test_download_thread_stores_raw_url_and_paths():
    """Regression: __init__ must not pre-quote url/path/path_selected.
    Pre-quoting breaks dirname(), subprocess list-mode, and double-quoted
    curl interpolations."""
    thread = DownloadThread(
        url="https://example.com/a file.qcow2",
        path="/disks/a path/file.qcow2",
        path_selected="/disks/a path",
        table="media",
        id_down="m-1",
        dict_header={},
        finalished_threads=[],
        threads_disk_operations={},
        pool_id="pool-1",
        type_path_selected="media",
    )
    assert thread.url == "https://example.com/a file.qcow2"
    assert thread.path == "/disks/a path/file.qcow2"
    assert thread.path_selected == "/disks/a path"


def test_execute_removes_pending_item_by_identity():
    """Regression: execute() must remove the matching pending entry
    from storage_pending[pool_id] after dispatch. Previously a bare
    `except: pass` masked list.remove failures."""
    thread = _thread()
    item = MagicMock(id="m-1", category="cat-a", table="media", status="Downloading")
    with patch(
        "engine.services.threads.download_thread.get_category_storage_pool_id",
        return_value="pool-1",
    ):
        thread.manager.diskoperations_pools = {
            "pool-1": MagicMock(
                balancer=MagicMock(get_next_diskoperations=MagicMock(return_value=True))
            )
        }
        thread.storage_pending = {
            "pool-1": [{"action": "start_download", "item": item}]
        }
        with patch.object(thread, "start_download"):
            thread.execute("start_download", item)
    assert thread.storage_pending["pool-1"] == []


def test_execute_warns_when_pending_item_missing():
    """Regression: when no matching pending entry exists, execute() must
    log a warning via logs.downloads.warning instead of silently swallowing
    the ValueError from list.remove (prior bare `except: pass`)."""
    thread = _thread()
    item = MagicMock(id="m-2", category="cat-b", table="media", status="Downloading")
    with patch(
        "engine.services.threads.download_thread.get_category_storage_pool_id",
        return_value="pool-2",
    ), patch("engine.services.threads.download_thread.logs") as mock_logs:
        thread.manager.diskoperations_pools = {
            "pool-2": MagicMock(
                balancer=MagicMock(get_next_diskoperations=MagicMock(return_value=True))
            )
        }
        thread.storage_pending = {}
        with patch.object(thread, "start_download"):
            thread.execute("start_download", item)
        mock_logs.downloads.warning.assert_called_once()
        msg = mock_logs.downloads.warning.call_args.args[0]
        assert "no pending entry" in msg.lower()
        assert "pool-2" in msg
        assert "start_download" in msg
        assert "m-2" in msg


def test_build_curl_command_quotes_path_and_url_once():
    """Regression: the curl command must shell-quote path and url exactly
    once at the interpolation site, not again on top of a pre-quoted value."""
    raw_url = "https://example.com/a file.qcow2"
    raw_path = "/disks/a path/file.qcow2"
    # Simulate the string the code should build (line 242 in download_thread.py).
    insecure_option = ""
    headers = ""
    curl_cmd = (
        f"curl {insecure_option} -L --max-redirs 5 --connect-timeout 30 "
        f"--no-netrc -o {shlex.quote(raw_path)} {headers} {shlex.quote(raw_url)}"
    )
    # Asserts the quoted form round-trips through shlex.split exactly.
    tokens = shlex.split(curl_cmd)
    assert raw_path in tokens
    assert raw_url in tokens
    # And dirname() on the raw value is clean (no stray quote chars).
    assert dirname(raw_path) == "/disks/a path"
