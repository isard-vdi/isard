# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every ``Error("<key>", ...)`` names a key of the error table, or it raises KeyError."""

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ex
from isardvdi_common.helpers.error_factory import Error

_COMPONENT = Path(__file__).resolve().parents[3]
_SOURCES = sorted(
    p
    for root in ("_common/src", "apiv4/src")
    if (_COMPONENT / root).is_dir()
    for p in (_COMPONENT / root).rglob("*.py")
)


def _literal_keys(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        args = node.args
        if name == "create":
            # Error.create(request, "<key>", ...)
            if not (isinstance(func.value, ast.Name) and func.value.id == "Error"):
                continue
            args = args[1:]
        elif name != "Error":
            continue
        if (
            args
            and isinstance(args[0], ast.Constant)
            and isinstance(args[0].value, str)
        ):
            yield node.lineno, args[0].value


def test_the_sources_are_found():
    assert len(_SOURCES) > 100


def test_every_literal_error_key_exists():
    unknown = [
        f"{path.relative_to(_COMPONENT)}:{line}: {key!r}"
        for path in _SOURCES
        for line, key in _literal_keys(path)
        if key not in ex
    ]
    assert unknown == []


class _Ctx:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_a_restore_whose_storage_update_fails_is_a_404(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    monkeypatch.setattr(mod.RethinkSharedConnection, "_rdb_context", _Ctx)

    def _table(name):
        if name == "storage":
            raise RuntimeError("storage update failed")
        return MagicMock(name=f"table-{name}")

    monkeypatch.setattr(mod.r, "table", _table)
    monkeypatch.setattr(mod, "_exists_now", lambda table, item_id: True)
    monkeypatch.setattr(mod.RecycleBin, "check_can_restore", lambda s: None)
    monkeypatch.setattr(mod.Helpers, "claim_status", classmethod(lambda cls, *a: True))
    rb = object.__new__(mod.RecycleBin)
    rb.id, rb.item_type, rb.owner_id, rb.owner_name = "rb-1", "desktop", "u", "u"
    rb.status = mod.RecycleBinStatusEnum.recycled.value
    rb.users, rb.groups, rb.categories, rb.storages = [], [], [], []

    with pytest.raises(Error) as exc:
        rb.restore()
    assert exc.value.status_code == 404
