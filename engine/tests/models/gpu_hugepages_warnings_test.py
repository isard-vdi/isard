# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hypervisor warnings for GPU hosts whose GPU desktops would start with 4K pages."""

from engine.models.memory_placement import gpu_hugepages_warnings, nvidia_gpu_numa_nodes

POOL = {"mounted": True, "1G": {"total": 336}, "2M": {"total": 0}}
GPU = {"vendor": "10de", "class_code": "030200"}


def test_a_host_without_gpus_has_no_warning():
    assert gpu_hugepages_warnings([], {}) == []


def test_a_gpu_host_without_a_pool_warns():
    assert gpu_hugepages_warnings([0], {"mounted": True}) == [
        "no hugepage pool: GPU desktops start with 4K pages "
        "(slow VFIO mapping, up to the extended createXML timeout)"
    ]


def test_a_gpu_host_with_an_unmounted_pool_warns():
    assert len(gpu_hugepages_warnings([None], {**POOL, "mounted": False})) == 1


def test_a_gpu_host_with_a_pool_and_no_numa_data_has_no_warning():
    assert gpu_hugepages_warnings([1], POOL) == []


def test_the_gpu_node_without_hugepages_warns_and_the_other_does_not():
    info = {**POOL, "numa": {"0": {"1G": 336, "2M": 0}, "1": {"1G": 0, "2M": 0}}}
    assert gpu_hugepages_warnings([0, 1, 1], info) == [
        "NUMA node 1 has GPUs but no hugepages: its GPU desktops get "
        "memory from another node or 4K pages"
    ]


def test_2m_pages_on_the_gpu_node_count_as_a_pool():
    info = {**POOL, "numa": {"0": {"1G": 0, "2M": 1024}}}
    assert gpu_hugepages_warnings([0], info) == []


def test_only_nvidia_display_controllers_are_gpus():
    pci = {
        "0000:41:00.0": {**GPU, "numa_node": 1},
        "0000:41:00.1": {"vendor": "10de", "class_code": "040300", "numa_node": 1},
        "0000:01:00.0": {"vendor": "8086", "class_code": "030000", "numa_node": 0},
        "0000:c1:00.0": {**GPU, "numa_node": -1},
    }
    assert sorted(nvidia_gpu_numa_nodes(pci), key=str) == [1, None]


def test_no_pci_devices_means_no_gpus():
    assert nvidia_gpu_numa_nodes(None) == []
