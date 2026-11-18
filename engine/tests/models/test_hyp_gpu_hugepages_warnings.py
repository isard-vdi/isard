# SPDX-License-Identifier: AGPL-3.0-or-later
"""A GPU host without hugepages for its GPUs says so in its gpu_warnings."""

import logging
from types import SimpleNamespace

import pytest

from engine.models import hyp as hyp_mod
from engine.models.hyp import hyp

GPU = {"vendor": "10de", "class_code": "030200", "numa_node": 1}


@pytest.fixture
def stored(monkeypatch):
    fields = {}
    monkeypatch.setattr(
        hyp_mod,
        "logs",
        SimpleNamespace(workers=logging.getLogger(__name__)),
        raising=False,
    )
    monkeypatch.setattr(
        hyp_mod,
        "update_table_field",
        lambda table, _id, field, value, **kw: fields.__setitem__(field, value),
    )
    return fields


def _init(hugepages_info):
    h = hyp.__new__(hyp)
    h.id_hyp_rethink = "isard-hypervisor"
    h.hypervisor = {
        "nvidia_gpus": [{"pci_bus_id": "0000:41:00.0", "warnings": ["w"]}],
        "pci_devices": {"0000:41:00.0": GPU},
        "hugepages_info": hugepages_info,
    }
    h.init_nvidia()


def test_a_gpu_host_without_a_pool_stores_the_warning(stored):
    _init({"mounted": False})
    assert stored["gpu_warnings"][0] == "GPU 0000:41:00.0: w"
    assert stored["gpu_warnings"][1].startswith("no hugepage pool")


def test_a_gpu_host_with_a_pool_on_its_gpu_node_stores_only_discovery(stored):
    _init({"mounted": True, "1G": {"total": 8}, "numa": {"1": {"1G": 8}}})
    assert stored["gpu_warnings"] == ["GPU 0000:41:00.0: w"]
