"""Unit tests for the pure vGPU grouping helpers in ``reservables``.

``_pci_id_to_sysfs`` and ``_tag_vgpus_with_groups`` are the dependency-free part
of the module: they carry the (server, NUMA-socket) grouping logic the attach
UIs depend on and touch no DB.
"""

import pytest
from isardvdi_common.lib.bookings.reservables import (
    _pci_id_to_sysfs,
    _tag_vgpus_with_groups,
)

# --- _pci_id_to_sysfs --------------------------------------------------------


@pytest.mark.parametrize(
    "underscored,expected",
    [
        ("0000_41_00_0", "0000:41:00.0"),
        ("0000_86_00_0", "0000:86:00.0"),
        ("0000_3b_00_0", "0000:3b:00.0"),
    ],
)
def test_pci_id_to_sysfs(underscored, expected):
    assert _pci_id_to_sysfs(underscored) == expected


# --- _tag_vgpus_with_groups --------------------------------------------------


def test_groups_and_numa_anonymized():
    vgpus = [{"id": "A"}, {"id": "B"}]
    hyp_map = {"A": ["hypX", "hypY"], "B": ["hypX"]}
    placements = {
        "A": {"hypX": {0, 1}, "hypY": {0}},
        "B": {"hypX": {1}},
    }
    out = _tag_vgpus_with_groups(vgpus, hyp_map, placements, show_names=False)
    a, b = out[0], out[1]
    # hypX -> 1, hypY -> 2 (sorted, 1-indexed)
    assert a["hypervisor_groups"] == [1, 2]
    assert b["hypervisor_groups"] == [1]
    assert a["numa_by_group"] == {"1": [0, 1], "2": [0]}
    assert b["numa_by_group"] == {"1": [1]}
    # Anonymized: no real names leaked when show_names is False.
    assert "hypervisors" not in a
    assert "numa_by_hypervisor" not in a


def test_show_names_adds_real_names():
    vgpus = [{"id": "A"}]
    hyp_map = {"A": ["hypX"]}
    placements = {"A": {"hypX": {0}}}
    out = _tag_vgpus_with_groups(vgpus, hyp_map, placements, show_names=True)
    assert out[0]["hypervisors"] == ["hypX"]
    assert out[0]["numa_by_hypervisor"] == {"hypX": [0]}


def test_single_socket_or_unknown_numa_yields_no_socket_layer():
    # A reservable whose cards have no real NUMA placement (single-socket /
    # unknown -> dropped upstream) gets an empty numa map: the UI shows no socket.
    vgpus = [{"id": "A"}]
    hyp_map = {"A": ["hypX"]}
    placements = {}  # nothing recorded
    out = _tag_vgpus_with_groups(vgpus, hyp_map, placements, show_names=True)
    assert out[0]["hypervisor_groups"] == [1]
    assert out[0]["numa_by_group"] == {}
    assert out[0]["numa_by_hypervisor"] == {}


def test_non_list_input_is_passthrough():
    assert _tag_vgpus_with_groups(None, {}, {}, False) is None
