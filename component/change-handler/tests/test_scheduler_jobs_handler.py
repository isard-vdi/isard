# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.handlers.scheduler_jobs import SchedulerJobsHandler
from pydantic import BaseModel
from tests.conftest import FakeChange, FakeRow


class JobRow(BaseModel):
    id: str
    name: Optional[str] = None
    kind: Optional[str] = None
    type: Optional[str] = None
    next_run_time: Optional[float] = None


@pytest.fixture
def sio():
    return AsyncMock()


@pytest.fixture
def handler(sio):
    return SchedulerJobsHandler(sio, "scheduler_jobs")


def _emitted(sio):
    return [(c.args[0], json.loads(c.args[1])) for c in sio.emit.await_args_list]


def test_the_scheduler_jobs_table_uses_the_filtering_handler():
    # __main__ needs the generated changefeed subscribers, so read it instead.
    main = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "isardvdi_change_handler"
        / "__main__.py"
    ).read_text()
    assert '"scheduler_jobs": SchedulerJobsHandler(' in main


@pytest.mark.asyncio
async def test_system_job_insert_reaches_the_admin_table(handler, sio):
    row = JobRow(id="system.x", name="x", kind="cron", type="system")
    await handler.handle(FakeChange(new_val=row, old_val=None))
    [(event, payload)] = _emitted(sio)
    assert event == "scheduler_jobs_add"
    assert payload["id"] == "system.x"
    assert sio.emit.await_args.kwargs == {
        "namespace": "/administrators",
        "room": "admins",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type", ["bookings", "alerts", None])
async def test_non_system_jobs_are_not_emitted(handler, sio, job_type):
    row = JobRow(id="j", name="desktop stop", kind="date", type=job_type)
    await handler.handle(FakeChange(new_val=row, old_val=None))
    await handler.handle(FakeChange(new_val=row, old_val=row))
    await handler.handle(FakeChange(new_val=None, old_val=row))
    sio.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_system_job_update_and_delete_are_emitted(handler, sio):
    old = JobRow(id="system.x", type="system", next_run_time=1.0)
    new = JobRow(id="system.x", type="system", next_run_time=2.0)
    await handler.handle(FakeChange(new_val=new, old_val=old))
    await handler.handle(FakeChange(new_val=None, old_val=new))
    assert [event for event, _ in _emitted(sio)] == [
        "scheduler_jobs_update",
        "scheduler_jobs_delete",
    ]


@pytest.mark.asyncio
async def test_type_carried_as_an_additional_property_is_honoured(handler, sio):
    row = FakeRow(id="system.x", additional_properties={"type": "system"})
    await handler.handle(FakeChange(new_val=row, old_val=None))
    other = FakeRow(id="b", additional_properties={"type": "bookings"})
    await handler.handle(FakeChange(new_val=other, old_val=None))
    assert [payload["id"] for _, payload in _emitted(sio)] == ["system.x"]
