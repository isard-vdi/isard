"""Unit tests for the GPU model-token alias in api_hypervisors.

`api_hypervisors` cannot be imported bare (api/__init__ boots Flask), so —
mirroring api_hypervisors_overlay_mtu_test.py — we evaluate ONLY the
self-contained `_MODEL_ALIASES` + `_model_alias` block extracted from the module
source via runpy. The hypervisor twin in
docker/hypervisor/src/lib/gpu_discovery.py must stay consistent; the parity test
below enforces that the two alias maps are byte-for-byte equal.
"""

import ast
import os
import re
import runpy
import tempfile
import types

import pytest

_HERE = os.path.dirname(__file__)
_API_SRC = os.path.join(_HERE, "api_hypervisors.py")
_DISCOVERY_SRC = os.path.normpath(
    os.path.join(
        _HERE,
        "..",
        "..",
        "..",
        "..",
        "docker",
        "hypervisor",
        "src",
        "lib",
        "gpu_discovery.py",
    )
)


def _load_alias_block():
    src = open(_API_SRC).read()
    block = re.search(
        r"_MODEL_ALIASES = \{.*?return _MODEL_ALIASES\.get\(pci_device_id\)",
        src,
        re.S,
    )
    assert block, "could not locate _MODEL_ALIASES/_model_alias block"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(block.group(0) + "\n")
        tmp_path = tmp.name
    try:
        ns = runpy.run_path(tmp_path, run_name="_model_alias_under_test")
    finally:
        os.unlink(tmp_path)
    return types.SimpleNamespace(**ns)


m = _load_alias_block()


def test_model_alias_device_only_key():
    # 10de:2bb5 (RTX PRO 6000 Blackwell) is device-only aliased; subsystem
    # irrelevant.
    assert m._model_alias("10de:2bb5") == "RTXPro6000BlackwellDC"
    assert m._model_alias("10de:2bb5", "10de:204e") == "RTXPro6000BlackwellDC"


def test_model_alias_subsystem_qualified_key():
    # 10de:25b6 is the shared A2/A16 die-id, aliased to A16 ONLY for the A16
    # subsystem.
    assert m._model_alias("10de:25b6", "10de:14a9") == "A16"


def test_model_alias_does_not_conflate_a2():
    # Same die-id, a different subsystem (real A2) must NOT match the A16 alias.
    assert m._model_alias("10de:25b6", "10de:157e") is None
    # And without a subsystem we cannot safely claim A16 either.
    assert m._model_alias("10de:25b6") is None


def test_model_alias_unmapped_and_empty():
    assert m._model_alias("10de:2235") is None  # A40 — clean, no alias
    assert m._model_alias(None) is None
    assert m._model_alias("") is None


def _extract_alias_literal(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_MODEL_ALIASES" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"_MODEL_ALIASES not found in {path}")


def test_alias_maps_are_in_sync_across_api_and_hypervisor():
    api_map = _extract_alias_literal(_API_SRC)
    discovery_map = _extract_alias_literal(_DISCOVERY_SRC)
    assert api_map == discovery_map, (
        "api_hypervisors._MODEL_ALIASES and gpu_discovery._MODEL_ALIASES drifted; "
        "they must stay identical so registration and discovery agree on the token."
    )


def _load_resync_fn():
    """Extract the self-contained gpu_card_metadata_resync function (pure, no DB)
    so it can be unit-tested without booting Flask via api/__init__."""
    src = open(_API_SRC).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "gpu_card_metadata_resync"
        ):
            ns = {}
            exec(ast.get_source_segment(src, node), ns)
            return ns["gpu_card_metadata_resync"]
    raise AssertionError("gpu_card_metadata_resync not found in api_hypervisors.py")


_resync = _load_resync_fn()

_CLEAN = "NVIDIA RTX PRO 6000 Blackwell Server Edition"
_FALLBACK_DESC = (
    "Auto-discovered from NVIDIA GB202GL [RTX PRO 6000 Blackwell Server Edition]"
)


def test_resync_heals_stale_zero_gb_card():
    # Card first seen vfio-bound (0 GB + pci.ids die-label) now reads NVML-clean.
    out = _resync(
        {"memory": "0 GB", "description": _FALLBACK_DESC},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {"memory": "95 GB", "description": f"Auto-discovered from {_CLEAN}"}


def test_resync_noop_on_already_clean_card():
    out = _resync(
        {"memory": "95 GB", "description": f"Auto-discovered from {_CLEAN}"},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {}


def test_resync_preserves_admin_edited_description():
    # An admin-renamed description is not the auto-generated form -> keep it;
    # still heal the bogus memory.
    out = _resync(
        {"memory": "0 GB", "description": "Lab card 3 (do not touch)"},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {"memory": "95 GB"}


def test_resync_noop_when_card_still_vfio_bound():
    # No NVML reading yet (fresh memory 0) -> nothing to heal, no churn.
    out = _resync(
        {"memory": "0 GB", "description": _FALLBACK_DESC},
        {"memory_total_mb": 0, "name": _CLEAN},
    )
    assert out == {}
