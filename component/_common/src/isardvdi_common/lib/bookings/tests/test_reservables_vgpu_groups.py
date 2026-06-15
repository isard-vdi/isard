"""Unit tests for the pure vGPU grouping helpers in ``api_reservables``.

The twin ``reservables`` module pulls the whole isardvdi_common package on
import, so — mirroring ``test_gpu_model_alias.py`` — we extract ONLY the
self-contained ``_pci_id_to_sysfs`` and ``_tag_vgpus_with_groups``
functions from the module source via ``ast`` and exec them in isolation. These two
carry the (server, NUMA-socket) grouping logic the attach UIs depend on.
"""

import ast
import os

import pytest

_SRC = os.path.join(os.path.dirname(__file__), "..", "reservables.py")
_WANTED = {"_pci_id_to_sysfs", "_tag_vgpus_with_groups"}


def _load_helpers():
    tree = ast.parse(open(_SRC).read())
    funcs = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in _WANTED
    ]
    assert {f.name for f in funcs} == _WANTED, "could not locate both helpers"
    ns = {}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), _SRC, "exec"), ns)
    return ns


_H = _load_helpers()


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
    assert _H["_pci_id_to_sysfs"](underscored) == expected


# --- _tag_vgpus_with_groups --------------------------------------------------


def test_groups_and_numa_anonymized():
    vgpus = [{"id": "A"}, {"id": "B"}]
    hyp_map = {"A": ["hypX", "hypY"], "B": ["hypX"]}
    placements = {
        "A": {"hypX": {0, 1}, "hypY": {0}},
        "B": {"hypX": {1}},
    }
    out = _H["_tag_vgpus_with_groups"](vgpus, hyp_map, placements, show_names=False)
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
    out = _H["_tag_vgpus_with_groups"](vgpus, hyp_map, placements, show_names=True)
    assert out[0]["hypervisors"] == ["hypX"]
    assert out[0]["numa_by_hypervisor"] == {"hypX": [0]}


def test_single_socket_or_unknown_numa_yields_no_socket_layer():
    # A reservable whose cards have no real NUMA placement (single-socket /
    # unknown -> dropped upstream) gets an empty numa map: the UI shows no socket.
    vgpus = [{"id": "A"}]
    hyp_map = {"A": ["hypX"]}
    placements = {}  # nothing recorded
    out = _H["_tag_vgpus_with_groups"](vgpus, hyp_map, placements, show_names=True)
    assert out[0]["hypervisor_groups"] == [1]
    assert out[0]["numa_by_group"] == {}
    assert out[0]["numa_by_hypervisor"] == {}


def test_non_list_input_is_passthrough():
    assert _H["_tag_vgpus_with_groups"](None, {}, {}, False) is None
