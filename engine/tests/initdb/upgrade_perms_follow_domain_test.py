"""The v210 rule for a storage row's ``perms``: a parent or a template's disk
is read-only, a desktop's is writable, and a disk no domain references is left
alone. Loaded bare from ``upgrade_helpers.py`` like the other pure helpers."""

import runpy
import types

import pytest
from tests.helpers import SRC_ROOT

m = types.SimpleNamespace(
    **runpy.run_path(
        str(SRC_ROOT / "initdb" / "upgrade_helpers.py"), run_name="_perms_under_test"
    )
)


@pytest.mark.parametrize(
    "has_children,kinds,expected",
    [
        (True, {"desktop"}, ["r"]),  # a parent is read-only whatever uses it
        (False, {"template"}, ["r"]),
        (False, {"template", "desktop"}, ["r"]),  # shared by a template: its disk
        (False, {"desktop"}, ["r", "w"]),
        (False, set(), None),  # recycle bin / orphan / in creation: not ours to say
        (False, None, None),
    ],
)
def test_perms_for_disk(has_children, kinds, expected):
    assert m.perms_for_disk(has_children, kinds) == expected
