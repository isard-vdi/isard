# SPDX-License-Identifier: AGPL-3.0-or-later

"""Digging a base its descendants read, from the disk button or the bulk action,
is refused unless every descendant (by database chain and by qcow2 header) is
stopped. The nightly sweep does not ask for that gate."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _code(excinfo):
    err = excinfo.value
    return getattr(err, "description_code", None) or (
        err.error.get("description_code")
        if isinstance(getattr(err, "error", None), dict)
        else None
    )


def _bare():
    storage = Storage.__new__(Storage)
    object.__setattr__(storage, "id", "base-1")
    object.__setattr__(storage, "pending_actions", {})
    return storage


@contextmanager
def _dig_patches(stopped):
    with (
        patch.object(Storage, "path", new="/isard/templates/g/base-1.qcow2"),
        patch.object(Storage, "directory_path", new="/isard/templates/g", create=True),
        patch.object(Storage, "domains", new=[]),
        patch.object(Storage, "descendants_all_stopped", return_value=stopped),
        patch("isardvdi_common.models.storage.disk_actions.is_base", return_value=True),
        patch.object(Storage, "set_maintenance"),
        patch.object(Storage, "_maintenance_release_statuses", return_value={}),
        patch.object(Storage, "create_task", return_value="t-1") as create,
        patch(
            "isardvdi_common.models.storage.StoragePool.get_best_for_action",
            return_value=SimpleNamespace(id="pool"),
        ),
    ):
        yield create


def test_a_base_with_a_running_descendant_is_refused():
    with _dig_patches(stopped=False):
        with pytest.raises(Error) as excinfo:
            _bare().dig_holes("u1", require_descendants_stopped=True)
    assert _code(excinfo) == "storage_descendants_not_stopped"


def test_a_base_whose_descendants_are_all_stopped_is_dug():
    with _dig_patches(stopped=True) as create:
        task_id = _bare().dig_holes("u1", require_descendants_stopped=True)
    assert task_id == "t-1"
    # a base its descendants read is always verified
    assert create.call_args.kwargs["job_kwargs"]["kwargs"]["verify"] is True


def test_the_sweep_path_does_not_ask_for_the_stopped_gate():
    """Without the flag (the nightly pass), a running descendant does not refuse:
    the sweep leans on verify, not on the descendants being stopped."""
    with _dig_patches(stopped=False) as create:
        task_id = _bare().dig_holes("u1", verify=True)
    assert task_id == "t-1"


class TestDescendantsAllStopped:
    def _dom(self, status):
        return SimpleNamespace(status=status)

    @contextmanager
    def _env(self, db_domains, header_dependents, header_rows, ok=True, unreadable=()):
        scan = {
            "dependents": list(header_dependents),
            "unreadable": list(unreadable),
            "ok": ok,
            "reason": None,
        }
        with (
            patch.object(Storage, "path", new="/isard/templates/g/base-1.qcow2"),
            patch.object(
                Storage, "directory_path", new="/isard/templates/g", create=True
            ),
            patch.object(Storage, "domains_dependents", return_value=db_domains),
            patch(
                "isardvdi_common.lib.storage.storage.StorageProcessed.scan_on_disk_dependents",
                return_value=scan,
                create=True,
            ),
            patch.object(
                Storage,
                "get_by_path",
                side_effect=lambda p: SimpleNamespace(domains=header_rows.get(p)),
            ),
        ):
            yield

    def test_true_when_db_and_header_descendants_are_stopped(self):
        with self._env(
            db_domains=[self._dom("Stopped")],
            header_dependents=["/isard/templates/g/child.qcow2"],
            header_rows={"/isard/templates/g/child.qcow2": [self._dom("Stopped")]},
        ):
            assert Storage.__new__(Storage).descendants_all_stopped() is True

    def test_false_when_a_db_descendant_runs(self):
        with self._env(
            db_domains=[self._dom("Started")], header_dependents=[], header_rows={}
        ):
            assert Storage.__new__(Storage).descendants_all_stopped() is False

    def test_false_when_a_header_descendant_runs(self):
        with self._env(
            db_domains=[],
            header_dependents=["/isard/templates/g/child.qcow2"],
            header_rows={"/isard/templates/g/child.qcow2": [self._dom("Started")]},
        ):
            assert Storage.__new__(Storage).descendants_all_stopped() is False

    @pytest.mark.parametrize(
        "kw", [{"ok": False}, {"unreadable": ["/isard/templates/g/x.qcow2"]}]
    )
    def test_fails_closed_when_the_header_scan_is_untrustworthy(self, kw):
        with self._env(db_domains=[], header_dependents=[], header_rows={}, **kw):
            assert Storage.__new__(Storage).descendants_all_stopped() is False
