"""Unit test for the multi-profile NUMA co-placement helper in ``hypervisors``.

``services/db/hypervisors`` cannot be imported bare (it pulls the engine's DB and
logging stack), so — like the API grouping test — we ast-extract ONLY the
self-contained ``_free_numa_nodes_for_profile`` function and exec it with stubs
for the two globals it calls (``profile_suffix_from_id``, ``get_vgpus_mdevs``).
This is the per-(host, profile) free-NUMA-node scan whose intersection seeds a
multi-profile desktop onto a shared socket.
"""

import ast
import os

# Lives under engine/models (not next to its target): the engine test
# conftest stubs the whole ``engine.services.db`` package in sys.modules, so
# pytest cannot import test modules from inside that package. The function
# under test is AST-extracted from the source file by path anyway.
_SRC = os.path.join(os.path.dirname(__file__), "..", "services", "db", "hypervisors.py")


def _load():
    tree = ast.parse(open(_SRC).read())
    fn = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_free_numa_nodes_for_profile"
    ]
    assert fn, "could not locate _free_numa_nodes_for_profile"
    ns = {
        "profile_suffix_from_id": lambda rid: rid.split("-")[-1],
        "get_vgpus_mdevs": _stub_mdevs,
    }
    exec(compile(ast.Module(body=fn, type_ignores=[]), _SRC, "exec"), ns)
    return ns["_free_numa_nodes_for_profile"]


def _free(profile):
    # 4Q has a free mdev on both cards; 8Q only on the node-0 card.
    return {"created": True, "domain_reserved": False, "domain_started": False}


def _stub_mdevs(gpu_id, gpu_profile):
    free = {
        ("h1-pci_0000_41_00_0", "4Q"): {"u1": _free("4Q")},
        ("h1-pci_0000_86_00_0", "4Q"): {"u2": _free("4Q")},
        ("h1-pci_0000_41_00_0", "8Q"): {"u3": _free("8Q")},
    }.get((gpu_id, gpu_profile), {})
    return (gpu_profile, {gpu_profile: free}, None)


_HOST = {
    "id": "h1",
    "info": {"nvidia": {"pci_0000_41_00_0": "A40", "pci_0000_86_00_0": "A40"}},
    "pci_devices": {
        "0000:41:00.0": {"numa_node": 0},
        "0000:86:00.0": {"numa_node": 1},
    },
}


def test_free_nodes_span_both_sockets():
    f = _load()
    assert f(_HOST, "NVIDIA-A40-4Q", None) == {0, 1}


def test_free_nodes_restricted_to_one_socket():
    f = _load()
    assert f(_HOST, "NVIDIA-A40-8Q", None) == {0}


def test_intersection_picks_shared_socket():
    f = _load()
    a = f(_HOST, "NVIDIA-A40-4Q", None)  # {0,1}
    b = f(_HOST, "NVIDIA-A40-8Q", None)  # {0}
    assert a & b == {0}  # co-locate both profiles on node 0


def test_eligibility_filter_scopes_cards():
    f = _load()
    assert f(_HOST, "NVIDIA-A40-4Q", {"h1-pci_0000_86_00_0"}) == {1}
