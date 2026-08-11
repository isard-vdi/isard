#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``convert`` must tell the measurement which format it just wrote.

``qemu_img_info_backing_chain`` pins ``-f`` instead of letting qemu-img probe,
so the caller owns the format. Every disk IsardVDI creates itself is qcow2 --
except the one ``convert`` produces, which is the whole point of the action.

Measured as qcow2, a perfectly good vmdk fails with
``qemu-img: Could not open '<the file itself>': Image is not in qcow2 format``.
The task's error branch matches that path against the path it was asked about,
they are equal, and it concludes the file is gone: the destination row is set
to ``deleted`` while the file sits on disk. The convert reports success, the
user never sees the disk, and nothing ever reclaims it.

These read the source rather than run the chain: the chain is a dict of
dependents handed to RQ, so the declaration is the behaviour.
"""

import ast
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parents[1] / "storage.py"
_REFRESH = "qemu_img_info_backing_chain"


def _convert_source():
    text = _SOURCE.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Storage":
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "convert"
                ):
                    return ast.get_source_segment(text, item) or ""
    raise AssertionError("Storage.convert not found in models/storage.py")


CONVERT = _convert_source()


def test_the_scan_found_convert_at_all():
    """A guard on the guard: an empty body passes everything below vacuously."""
    assert _REFRESH in CONVERT, "convert no longer enqueues the refresh at all"


def test_convert_declares_the_destination_format_to_the_refresh():
    """The refresh kwargs must carry storage_type, not just id and path."""
    tree = ast.parse(CONVERT)
    kwarg_dicts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(
            isinstance(k, ast.Constant) and k.value == "storage_path" for k in node.keys
        )
    ]
    assert kwarg_dicts, "no storage_path kwargs dict found in convert's chain"
    for d in kwarg_dicts:
        keys = {k.value for k in d.keys if isinstance(k, ast.Constant)}
        assert "storage_type" in keys, (
            "convert hands the refresh a path but not the format it wrote. The "
            "refresh pins -f qcow2 by default, so a vmdk/raw destination is "
            "measured as qcow2, fails to open, and the row is set to deleted "
            "while the file stays on disk."
        )


def test_the_refresh_is_told_the_new_type_not_the_source_type():
    """``self.type`` is the SOURCE's format; passing it would defeat the point."""
    assert "dest_type" in CONVERT, (
        "convert should derive one normalised destination format and pass it "
        "to both the convert task and the refresh"
    )
    assert '"storage_type": self.type' not in CONVERT
    assert "'storage_type': self.type" not in CONVERT


@pytest.mark.parametrize("consumer", ["format", "storage_type"])
def test_both_the_write_and_the_measure_use_the_same_normalised_format(consumer):
    """qemu-img is case-sensitive on -f; one lowering, used by both."""
    assert f'"{consumer}": dest_type' in CONVERT, (
        f"{consumer} should be the shared, already-lowered dest_type so the "
        "file is written and measured as the same thing"
    )
