# SPDX-License-Identifier: AGPL-3.0-or-later
"""update_storages: model-to-dict access and the read-only out-of-pool classifier."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

import pytest  # noqa: E402

pytest.importorskip(
    "isardvdi_apiv4_client.client",
    reason="the generated apiv4 client is produced by codegen",
)


def _load():
    loader = SourceFileLoader("update_storages_cli", str(_UTILS / "update_storages"))
    spec = importlib.util.spec_from_loader("update_storages_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


mod = _load()

POOL = "/isard/storage_pools/default"
PREFIXES = [POOL]


class _FakeModel:
    """A generated-client model exposes to_dict(); that is what the fix relies on."""

    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return dict(self._d)


def test_as_dict_flattens_models_and_lists():
    assert mod._as_dict(_FakeModel({"status": "ready"})) == {"status": "ready"}
    assert mod._as_dict([_FakeModel({"id": "x"})]) == [{"id": "x"}]
    assert mod._as_dict(None) is None


def test_classify_bad_path_when_file_is_off_its_pool_location():
    storages = [
        {"id": "ok", "directory_path": f"{POOL}/desktops", "type": "qcow2"},
        {"id": "gone", "directory_path": f"{POOL}/desktops", "type": "qcow2"},
    ]
    present = {f"{POOL}/desktops/ok.qcow2"}
    buckets = mod.classify_out_of_pool(
        storages, PREFIXES, path_exists=lambda p: p in present
    )
    assert [i["id"] for i in buckets["bad_path"]] == ["gone"]
    assert buckets["not_in_pool"] == []


def test_classify_not_in_pool_when_directory_is_outside_every_pool():
    storages = [
        {"id": "legacy", "directory_path": "/isard/groups/legacy", "type": "qcow2"}
    ]
    buckets = mod.classify_out_of_pool(storages, PREFIXES, path_exists=lambda p: True)
    assert [i["id"] for i in buckets["not_in_pool"]] == ["legacy"]
    assert buckets["bad_path"] == []


def test_classify_ok_when_file_is_at_its_pool_path():
    storages = [{"id": "good", "directory_path": f"{POOL}/desktops", "type": "qcow2"}]
    buckets = mod.classify_out_of_pool(storages, PREFIXES, path_exists=lambda p: True)
    assert buckets["not_in_pool"] == []
    assert buckets["bad_path"] == []
