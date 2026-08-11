# SPDX-License-Identifier: AGPL-3.0-or-later

"""``set_maintenance``/``set_ready`` preconditions must reach the caller typed.

Both methods refuse to act when the storage is in the wrong state, has a
running desktop, or has backing children. They stated those refusals as a bare
``Exception`` carrying a 3-tuple, which apiv4 cannot map: its route handlers
match ``except Error`` first and only then fall through to a generic
``except Exception``, so a precondition arrived at the client as
**500 "Failed to convert storage"** with the reason swallowed.

Sixteen call sites go through ``set_maintenance`` — every storage operation
that has to lock the disk first — so the refusal is stated once, here, and
every one of them answers 428 with a description code the frontend can
translate.

These tests never touch RethinkDB: instances are built via ``__new__`` and only
the attributes each branch reads are set.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _bare(status, domains=(), children=()):
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = "s-1"
    storage.__dict__["status"] = status
    storage.__dict__["_domains"] = list(domains)
    storage.__dict__["_children"] = list(children)
    type(storage).domains = property(lambda self: self.__dict__["_domains"])
    type(storage).children = property(lambda self: self.__dict__["_children"])
    return storage


class _Domain:
    def __init__(self, status="Stopped"):
        self.status = status
        self.current_action = None


def _code(excinfo):
    """The description_code, wherever this Error flavour keeps it."""
    err = excinfo.value
    return getattr(err, "description_code", None) or (
        err.error.get("description_code")
        if isinstance(getattr(err, "error", None), dict)
        else None
    )


def test_a_storage_that_is_not_ready_refuses_with_a_typed_error():
    storage = _bare("maintenance")

    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("convert")

    assert _code(excinfo) == "storage_not_ready"


def test_a_move_from_the_wrong_status_refuses_with_a_typed_error():
    storage = _bare("creating")

    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("move")

    assert _code(excinfo) == "storage_invalid_status_for_move"


def test_a_running_desktop_refuses_with_a_typed_error():
    storage = _bare("ready", domains=[_Domain(status="Started")])

    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("convert")

    assert _code(excinfo) == "desktops_not_stopped"


def test_a_disk_with_backing_children_refuses_with_a_typed_error():
    """The case that answered 500 on convert and 428 on sparsify."""
    storage = _bare("ready", children=["child-1"])

    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("convert")

    assert _code(excinfo) == "storage_has_children"


def test_returning_to_ready_from_the_wrong_status_refuses_with_a_typed_error():
    storage = _bare("ready")

    with pytest.raises(Error) as excinfo:
        storage.set_ready()

    assert _code(excinfo) == "storage_not_maintenance"
