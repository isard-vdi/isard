# SPDX-License-Identifier: AGPL-3.0-or-later

"""A template whose disk copy the worker refused hands its desktop back."""

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
        domain.handle_template_copy_refused(
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


@pytest.mark.parametrize(
    "step",
    [
        # the copy ran (or got past the refusal) and failed: the file may be gone
        _step(meta={}),
        # the move succeeded: nothing to hand back
        _step(depending_status="finished", meta={"source_untouched": True}),
        # a cancel is not a refusal: the worker may have finished the copy
        _step(depending_status="canceled", meta={"source_untouched": True}),
    ],
)
def test_nothing_is_handed_back_unless_the_worker_refused(step):
    from isardvdi_change_handler.task_results import domain

    with (
        patch.object(domain, "Domain") as dom,
        patch.object(domain, "Storage") as sto,
    ):
        domain.handle_template_copy_refused(step, **KW)
    dom.update_document_if.assert_not_called()
    sto.write_status.assert_not_called()


def test_the_step_is_registered():
    from isardvdi_change_handler.task_results import domain, registry

    handler, is_async = registry.HANDLERS["template_copy_refused"]
    assert handler is domain.handle_template_copy_refused
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
