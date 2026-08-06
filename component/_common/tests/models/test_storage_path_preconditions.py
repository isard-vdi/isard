# SPDX-License-Identifier: AGPL-3.0-or-later

"""``set_path`` / ``delete_path`` refusals must reach the caller typed.

Both guard the "edit disk path" modal: the id embedded in the path must match the
storage being edited, and the new path must differ from the current one. The second
is the guard-rail that stops the modal deleting the live disk.

They stated those refusals as a bare ``Exception`` carrying a tuple, and their apiv4
service methods are pure pass-throughs — so the route's ``except Error: raise`` never
matched and both arrived at the client as a **500** with the reason swallowed. Typed,
they arrive as 428 and 400 with the text the operator needs.

No RethinkDB: instances are built via ``__new__`` and only the attributes each branch
reads are set.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage

STORAGE_ID = "11111111-2222-3333-4444-555555555555"
OTHER_ID = "99999999-8888-7777-6666-555555555555"


def _bare(path):
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = STORAGE_ID
    type(storage).path = property(lambda self: path)
    return storage


def _code(excinfo):
    err = excinfo.value
    code = getattr(err, "description_code", None)
    if code:
        return code
    payload = getattr(err, "error", None)
    return payload.get("description_code") if isinstance(payload, dict) else None


@pytest.mark.parametrize("method", ["set_path", "delete_path"])
def test_a_path_naming_another_storage_is_refused_typed(method):
    storage = _bare(f"/isard/groups/{STORAGE_ID}.qcow2")

    with pytest.raises(Error) as excinfo:
        getattr(storage, method)("u1", f"/isard/groups/{OTHER_ID}.qcow2")

    assert excinfo.value.args[0] == "precondition_required"
    assert _code(excinfo) == "storage_id_mismatch"


@pytest.mark.parametrize("method", ["set_path", "delete_path"])
def test_the_current_path_is_refused_typed(method):
    """The guard-rail that stops the modal acting on the live disk."""
    path = f"/isard/groups/{STORAGE_ID}.qcow2"
    storage = _bare(path)

    with pytest.raises(Error) as excinfo:
        getattr(storage, method)("u1", path)

    assert excinfo.value.args[0] == "bad_request"


def test_an_owner_without_a_category_is_refused_typed(monkeypatch):
    """Reachable whenever a disk outlives the row of the user who owns it."""
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = STORAGE_ID
    type(storage).category = property(lambda self: None)

    with pytest.raises(Error) as excinfo:
        storage._require_category()

    assert excinfo.value.args[0] == "precondition_required"
    assert _code(excinfo) == "storage_owner_no_category"
