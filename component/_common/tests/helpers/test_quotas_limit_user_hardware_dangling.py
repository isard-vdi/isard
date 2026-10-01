# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Quotas.limit_user_hardware_allowed`` with references to rows that are gone."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import quotas as mod
from rethinkdb.errors import ReqlNonExistenceError

Q = mod.Quotas

ROWS = {
    "reservables_vgpus": {
        "None": {"id": "None", "name": "No GPU"},
        "GPU-8Q": {"id": "GPU-8Q", "name": "GPU 8192"},
    },
    "videos": {"default": {"id": "default", "name": "Default"}},
    "boots": {"disk": {"id": "disk", "name": "Hard Disk"}},
    "interfaces": {},
    "graphics": {},
    "media": {},
}


# Like ReQL: a field of a missing row raises unless a default is given.
class _Value:
    def __init__(self, row, field=None, default=None, has_default=False):
        self.row, self.field = row, field
        self._default, self._has_default = default, has_default

    def __getitem__(self, field):
        return _Value(self.row, field)

    def pluck(self, *fields):
        return _Value(self.row, ("pluck", fields))

    def default(self, value):
        return _Value(self.row, self.field, value, True)

    def run(self, conn):
        if self.row is None:
            if self._has_default:
                return self._default
            raise ReqlNonExistenceError("Cannot perform get_field on null")
        if isinstance(self.field, tuple):
            return {k: self.row[k] for k in self.field[1]}
        return self.row[self.field]


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def get(self, item_id):
        return _Value(self.rows.get(item_id))


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def quotas(monkeypatch):
    monkeypatch.setattr(Q, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(Q), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(mod.r, "table", lambda name: _Table(ROWS[name]))

    def allowed(allowed_vgpus=(), allowed_videos=("default",)):
        monkeypatch.setattr(
            Q,
            "user_hardware_allowed",
            classmethod(
                lambda cls, payload, *a, **kw: {
                    "quota": False,
                    "interfaces": [],
                    "videos": [{"id": v} for v in allowed_videos],
                    "graphics": [],
                    "boot_order": [{"id": "disk"}],
                    "reservables": {"vgpus": [{"id": v} for v in allowed_vgpus]},
                }
            ),
        )
        return Q

    return allowed


def _domain(vgpus, videos=("default",)):
    return {
        "hardware": {
            "vcpus": 1,
            "memory": 1,
            "videos": list(videos),
            "boot_order": ["disk"],
        },
        "reservables": {"vgpus": list(vgpus)},
    }


def test_a_profile_that_no_longer_exists_is_limited_by_id(quotas):
    q = quotas(allowed_vgpus=["GPU-8Q"])

    result = q.limit_user_hardware_allowed({}, _domain(["GPU-passthrough"]))

    assert result["reservables"]["vgpus"] is None
    assert result["limited_hardware"]["vgpus"] == {
        "old_value": [{"id": "GPU-passthrough", "name": "GPU-passthrough"}],
        "new_value": [{"id": "None", "name": "No GPU"}],
    }


def test_an_existing_profile_the_user_cannot_use_keeps_its_name(quotas):
    q = quotas(allowed_vgpus=[])

    result = q.limit_user_hardware_allowed({}, _domain(["GPU-8Q"]))

    assert result["limited_hardware"]["vgpus"]["old_value"] == [
        {"id": "GPU-8Q", "name": "GPU 8192"}
    ]


def test_every_disallowed_profile_is_removed_and_reported_alike(quotas):
    q = quotas(allowed_vgpus=[])

    result = q.limit_user_hardware_allowed({}, _domain(["GPU-8Q", "GPU-gone"]))

    assert result["reservables"]["vgpus"] is None
    assert result["limited_hardware"]["vgpus"]["old_value"] == [
        {"id": "GPU-8Q", "name": "GPU 8192"},
        {"id": "GPU-gone", "name": "GPU-gone"},
    ]


def test_a_missing_video_is_limited_by_id(quotas):
    q = quotas()

    result = q.limit_user_hardware_allowed({}, _domain([], videos=["qxl-gone"]))

    assert result["hardware"]["videos"] == ["default"]
    assert result["limited_hardware"]["videos"]["old_value"] == [
        {"id": "qxl-gone", "name": "qxl-gone"}
    ]


def test_an_allowed_profile_is_left_alone(quotas):
    q = quotas(allowed_vgpus=["GPU-8Q"])

    result = q.limit_user_hardware_allowed({}, _domain(["GPU-8Q"]))

    assert result["reservables"]["vgpus"] == ["GPU-8Q"]
    assert result["limited_hardware"] is None
