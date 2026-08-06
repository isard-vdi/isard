#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""An entry finishes when the work it started finishes, not when it has as many
finished tasks as it lists storages.

The delete loop skips a storage whose row no longer exists and one already
``deleted``, so an entry that mixes dead disks with live ones registers fewer
tasks than it has storages. Counting storages, such an entry can never reach its
own total: it frees what it can and then stays in ``deleting`` for good, which
its owner reads as a deletion that never ends.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def helpers(monkeypatch):
    """Drive ``update_task_status`` over a fake table, and report what it did.

    ``runs`` is the queue of results the two ``update(...).run()`` calls return,
    in order: the first is the per-task status write (which carries the entry as
    ``new_val``), the second the flip to ``deleted``.
    """
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Helpers),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    state = {"updates": 0, "logs": []}

    def _drive(entry):
        runs = [
            {"changes": [{"new_val": entry}]},
            {"changes": [{"new_val": dict(entry, status="deleted")}]},
        ]

        def fake_table(_name):
            table = MagicMock(name="table")

            def fake_update(*_a, **_kw):
                state["updates"] += 1
                result = MagicMock(name="update")
                result.run.return_value = runs.pop(0) if runs else {"changes": []}
                return result

            table.get.return_value.update.side_effect = fake_update
            return table

        monkeypatch.setattr(mod.r, "table", fake_table)
        monkeypatch.setattr(
            mod.Helpers,
            "add_log",
            staticmethod(lambda kind, *a, **kw: state["logs"].append(kind)),
        )
        mod.Helpers.update_task_status(
            {"id": "t1", "recycle_bin_id": "rb1", "status": "finished"}
        )
        # The first update is the per-task status write, which always happens.
        return {"flipped": state["updates"] > 1, "logs": list(state["logs"])}

    return _drive


def _entry(storages, tasks, status="deleting"):
    return {
        "id": "rb1",
        "status": status,
        "storages": storages,
        "tasks": tasks,
        "agent_type": "user",
        "agent_id": "u1",
        "agent_name": "u",
        "agent_category_id": "c1",
        "agent_category_name": "c",
        "agent_role": "admin",
    }


def test_an_entry_whose_every_task_finished_is_deleted(helpers):
    out = helpers(
        _entry(
            storages=[{"id": "s1"}, {"id": "s2"}],
            tasks=[
                {"id": "t1", "status": "finished"},
                {"id": "t2", "status": "finished"},
            ],
        )
    )
    assert out["flipped"] is True
    assert "deleted" in out["logs"]


def test_a_dead_disk_alongside_a_live_one_does_not_strand_the_entry(helpers):
    """Two storages, one already gone, so only one task was ever registered.

    This is the case that stayed in ``deleting`` for ever.
    """
    out = helpers(
        _entry(
            storages=[{"id": "gone"}, {"id": "live"}],
            tasks=[{"id": "t1", "status": "finished"}],
        )
    )
    assert out["flipped"] is True, "the entry never reached deleted"
    assert "deleted" in out["logs"]


def test_an_entry_with_work_still_running_is_left_alone(helpers):
    out = helpers(
        _entry(
            storages=[{"id": "s1"}, {"id": "s2"}],
            tasks=[
                {"id": "t1", "status": "finished"},
                {"id": "t2", "status": "queued"},
            ],
        )
    )
    assert out["flipped"] is False
    assert "deleted" not in out["logs"]


def test_an_entry_already_deleted_is_not_flipped_again(helpers):
    out = helpers(
        _entry(
            storages=[{"id": "s1"}],
            tasks=[{"id": "t1", "status": "finished"}],
            status="deleted",
        )
    )
    assert out["flipped"] is False
