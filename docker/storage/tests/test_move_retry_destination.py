# SPDX-License-Identifier: AGPL-3.0-or-later

"""``move`` must not take a destination left by a FAILED attempt as the copy.

The short-circuit at the top of ``move`` — same name, same size, same mtime ->
return without copying — exists so a redelivered task is idempotent. But rsync
preserves mtime, so the file a failed attempt leaves behind satisfies it too,
and the retry then returns in milliseconds having copied nothing: it reaches the
integrity gate with the same file and fails the same way, for ever.

Measured in production (gencat-fp, 19/09/2026): a second attempt on the same
26 GB disk returned 0 in 12 ms.
"""

import pytest


class _Stat:
    def __init__(self, dev, size=1):
        self.st_dev = dev
        self.st_size = size


def _fs(monkeypatch, task):
    """Origin and destination both present, and indistinguishable to _same_file."""
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "isdir", lambda p: True)
    monkeypatch.setattr(task, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(task, "_same_file", lambda a, b: True)
    monkeypatch.setattr(task, "os_stat", lambda p: _Stat(1))
    monkeypatch.setattr(task, "_free_space", lambda d: 1 << 40)


class TestRetryDoesNotTrustTheDestination:
    def test_a_retry_copies_even_when_the_destination_looks_identical(
        self, monkeypatch
    ):
        from isardvdi_storage import task

        _fs(monkeypatch, task)
        ran = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda cmd, *a, **k: ran.append(cmd) or 0
        )
        rc = task.move(
            "/isard/src/disk.qcow2",
            "/isard/dst/disk.qcow2",
            "rsync",
            remove_source_file=False,
            trust_existing_destination=False,
        )
        assert rc == 0
        assert ran, "the retry must copy; an identical-looking file proves nothing"
        assert ran[0][0] == "rsync"

    def test_the_default_still_short_circuits(self, monkeypatch):
        """A redelivered task that DID finish must stay a no-op."""
        from isardvdi_storage import task

        _fs(monkeypatch, task)
        ran = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda cmd, *a, **k: ran.append(cmd) or 0
        )
        assert (
            task.move(
                "/isard/src/disk.qcow2",
                "/isard/dst/disk.qcow2",
                "rsync",
                remove_source_file=False,
            )
            == 0
        )
        assert ran == []

    def test_a_retry_that_may_rename_still_copies(self, monkeypatch):
        """``auto`` with remove_source_file must not rename past the guard either."""
        from isardvdi_storage import task

        _fs(monkeypatch, task)
        renamed, removed, ran = [], [], []
        monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))
        monkeypatch.setattr(task, "remove", lambda p: removed.append(p))
        monkeypatch.setattr(
            task, "run_with_progress", lambda cmd, *a, **k: ran.append(cmd) or 0
        )
        task.move(
            "/isard/src/disk.qcow2",
            "/isard/dst/disk.qcow2",
            "auto",
            trust_existing_destination=False,
        )
        assert (
            removed == []
        ), "the source must not be dropped on the strength of a guess"
        assert renamed or ran, "the retry must actually place the file"
