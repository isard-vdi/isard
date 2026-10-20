# SPDX-License-Identifier: AGPL-3.0-or-later

"""A template whose root ``move`` failed with the desktop's file whole hands it back."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _step(depending_status="failed", meta=None):
    move = SimpleNamespace(job=SimpleNamespace(meta=meta or {}))
    return SimpleNamespace(
        id="step-1", depending_status=depending_status, dependencies=[move]
    )


KW = dict(
    desktop_id="d1",
    template_id="t1",
    template_storage_id="ts1",
    desktop_restore={"parents": ["base-1"]},
)


def test_a_refused_copy_hands_the_desktop_back():
    from isardvdi_change_handler.task_results import domain

    with (
        patch.object(domain, "Domain") as dom,
        patch.object(domain, "Storage") as sto,
    ):
        domain.handle_template_move_failed(
            _step(meta={domain.SOURCE_UNTOUCHED_META_KEY: True}), **KW
        )

    calls = {c.args[0]: c for c in dom.update_document_if.call_args_list}
    desktop = calls["d1"]
    assert desktop.args[1] == {"status": "Stopped", "parents": ["base-1"]}
    assert desktop.kwargs["field"] == "status"
    assert tuple(desktop.kwargs["values"]) == ("CreatingTemplate",)
    template = calls["t1"]
    assert template.args[1]["status"] == "Failed"
    assert template.args[1]["detail"] == domain.TEMPLATE_COPY_REFUSED_DETAIL
    assert tuple(template.kwargs["values"]) == ("CreatingTemplate",)
    # the never-written template disk; the desktop's own disk is not touched
    sto.write_status.assert_called_once_with("ts1", "deleted")


def test_a_finished_copy_whose_source_unlink_failed_hands_the_desktop_back():
    """The copy is whole and the source may still be there: nothing is deleted.

    The worker states ``copy_complete`` before the unlink, so the meta is the
    same whether the unlink raised (EIO, ESTALE) or hung until the job timeout.
    """
    from isardvdi_change_handler.task_results import domain

    step = _step(meta={domain.COPY_COMPLETE_META_KEY: True, "progress": 1})
    with (
        patch.object(domain, "Domain") as dom,
        patch.object(domain, "Storage") as sto,
    ):
        domain.handle_template_move_failed(step, **KW)

    calls = {c.args[0]: c for c in dom.update_document_if.call_args_list}
    assert calls["d1"].args[1] == {"status": "Stopped", "parents": ["base-1"]}
    assert tuple(calls["d1"].kwargs["values"]) == ("CreatingTemplate",)
    assert calls["t1"].args[1] == {
        "status": "Failed",
        "detail": domain.TEMPLATE_SOURCE_KEPT_DETAIL,
    }
    assert tuple(calls["t1"].kwargs["values"]) == ("CreatingTemplate",)
    # the copy is kept: the template disk row fails and is never marked deleted;
    # the desktop's own disk row is not touched at all
    sto.write_status.assert_called_once_with("ts1", "Failed")


def test_a_refusal_wins_over_a_copy_flag():
    """One run cannot state both; if it did, only the refused copy is known to
    have never written the template disk, so only it may mark it deleted."""
    from isardvdi_change_handler.task_results import domain

    step = _step(
        meta={
            domain.SOURCE_UNTOUCHED_META_KEY: True,
            domain.COPY_COMPLETE_META_KEY: True,
        }
    )
    with (
        patch.object(domain, "Domain"),
        patch.object(domain, "Storage") as sto,
    ):
        domain.handle_template_move_failed(step, **KW)
    sto.write_status.assert_called_once_with("ts1", "deleted")


@pytest.mark.parametrize(
    "step",
    [
        # the copy ran and failed before it ended: the worker said nothing
        _step(meta={}),
        _step(meta={"progress": 0.4}),
        # a finished move: nothing to hand back
        _step(depending_status="finished", meta={"copy_complete": True}),
        # a cancel stops rsync mid-copy: not a finished copy
        _step(depending_status="canceled", meta={"copy_complete": True}),
        # the move succeeded: nothing to hand back
        _step(depending_status="finished", meta={"source_untouched": True}),
        # a cancel is not a refusal: the worker may have finished the copy
        _step(depending_status="canceled", meta={"source_untouched": True}),
    ],
)
def test_nothing_is_handed_back_unless_the_worker_said_the_file_is_whole(step):
    from isardvdi_change_handler.task_results import domain

    with (
        patch.object(domain, "Domain") as dom,
        patch.object(domain, "Storage") as sto,
    ):
        domain.handle_template_move_failed(step, **KW)
    dom.update_document_if.assert_not_called()
    sto.write_status.assert_not_called()


def test_the_step_is_registered():
    from isardvdi_change_handler.task_results import domain, registry

    handler, is_async = registry.HANDLERS["template_move_failed"]
    assert handler is domain.handle_template_move_failed
    assert is_async is registry.SYNC


STATUSES = {
    "_all": {"x": {"storage": ["s-all"]}},
    "failed": {"Failed": {"domain": ["d1", "t1"], "storage": ["s1", "ts1"]}},
}
ONLY_WHILE = {"domain": "d1", "statuses": ["CreatingTemplate"]}


async def _update_status(desktop_status):
    from isardvdi_change_handler.task_results import storage

    domain_model = MagicMock()
    domain_model.build.return_value = (
        None if desktop_status is None else SimpleNamespace(status=desktop_status)
    )
    with (
        patch.object(
            storage, "_ITEM_CLASS_MAP", {"domain": domain_model, "storage": MagicMock()}
        ),
        patch.object(storage, "Storage") as sto,
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        sto.write_status.return_value = "x"
        await storage.handle_update_status(
            AsyncMock(),
            SimpleNamespace(id="u1", depending_status="failed"),
            statuses=STATUSES,
            only_while=ONLY_WHILE,
        )
    return domain_model, sto


@pytest.mark.asyncio
async def test_the_terminal_mapping_still_fails_a_desktop_that_is_parked():
    domain_model, sto = await _update_status("CreatingTemplate")
    written = [c.args for c in sto.write_status.call_args_list]
    assert ("s1", "Failed") in written and ("ts1", "Failed") in written
    assert {c.args[0] for c in domain_model.update_document.call_args_list} == {
        "d1",
        "t1",
    }


@pytest.mark.parametrize("desktop_status", ["Stopped", None])
@pytest.mark.asyncio
async def test_the_terminal_mapping_leaves_a_desktop_handed_back(desktop_status):
    """Handed back (or gone): the per-status branch is skipped; ``_all`` is not."""
    domain_model, sto = await _update_status(desktop_status)
    assert [c.args for c in sto.write_status.call_args_list] == [("s-all", "x")]
    domain_model.update_document.assert_not_called()


@pytest.mark.asyncio
async def test_without_only_while_nothing_changes():
    from isardvdi_change_handler.task_results import storage

    domain_model = MagicMock()
    with (
        patch.object(
            storage, "_ITEM_CLASS_MAP", {"domain": domain_model, "storage": MagicMock()}
        ),
        patch.object(storage, "Storage") as sto,
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        sto.write_status.return_value = "x"
        await storage.handle_update_status(
            AsyncMock(),
            SimpleNamespace(id="u1", depending_status="failed"),
            statuses=STATUSES,
        )
    domain_model.build.assert_not_called()
    assert ("s1", "Failed") in [c.args for c in sto.write_status.call_args_list]
