"""Unit tests for the GPU model-token alias in the hypervisors twin.

Port of api/src/api/libv2/api_hypervisors_gpu_model_test.py (upstream MR
!4496). The hypervisor twin in isardvdi_hypervisor/gpu_discovery.py must
stay consistent; the parity test below enforces that the two alias maps
are equal. That twin belongs to another workspace package, which is not
installed in the isardvdi-common test environment, so its
``_MODEL_ALIASES`` literal is read from the source with ``ast``.
"""

import ast
import pathlib

from isardvdi_common.lib.hypervisors.hypervisors import (
    _MODEL_ALIASES,
    _model_alias,
    gpu_card_metadata_resync,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
_DISCOVERY_SRC = (
    _REPO_ROOT
    / "docker"
    / "hypervisor"
    / "src"
    / "isardvdi_hypervisor"
    / "gpu_discovery.py"
)


def test_model_alias_device_only_key():
    # 10de:2bb5 (RTX PRO 6000 Blackwell) is device-only aliased; subsystem
    # irrelevant.
    assert _model_alias("10de:2bb5") == "RTXPro6000BlackwellDC"
    assert _model_alias("10de:2bb5", "10de:204e") == "RTXPro6000BlackwellDC"


def test_model_alias_subsystem_qualified_key():
    # 10de:25b6 is the shared A2/A16 die-id, aliased to A16 ONLY for the A16
    # subsystem.
    assert _model_alias("10de:25b6", "10de:14a9") == "A16"


def test_model_alias_does_not_conflate_a2():
    # Same die-id, a different subsystem (real A2) must NOT match the A16 alias.
    assert _model_alias("10de:25b6", "10de:157e") is None
    # And without a subsystem we cannot safely claim A16 either.
    assert _model_alias("10de:25b6") is None


def test_model_alias_unmapped_and_empty():
    assert _model_alias("10de:2235") is None  # A40 — clean, no alias
    assert _model_alias(None) is None
    assert _model_alias("") is None


def _extract_alias_literal(path):
    tree = ast.parse(pathlib.Path(path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_MODEL_ALIASES" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"_MODEL_ALIASES not found in {path}")


def test_alias_maps_are_in_sync_across_api_and_hypervisor():
    discovery_map = _extract_alias_literal(_DISCOVERY_SRC)
    assert _MODEL_ALIASES == discovery_map, (
        "hypervisors._MODEL_ALIASES and gpu_discovery._MODEL_ALIASES drifted; "
        "they must stay identical so registration and discovery agree on the token."
    )


_CLEAN = "NVIDIA RTX PRO 6000 Blackwell Server Edition"
_FALLBACK_DESC = (
    "Auto-discovered from NVIDIA GB202GL [RTX PRO 6000 Blackwell Server Edition]"
)


def test_resync_heals_stale_zero_gb_card():
    # Card first seen vfio-bound (0 GB + pci.ids die-label) now reads NVML-clean.
    out = gpu_card_metadata_resync(
        {"memory": "0 GB", "description": _FALLBACK_DESC},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {"memory": "95 GB", "description": f"Auto-discovered from {_CLEAN}"}


def test_resync_noop_on_already_clean_card():
    out = gpu_card_metadata_resync(
        {"memory": "95 GB", "description": f"Auto-discovered from {_CLEAN}"},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {}


def test_resync_preserves_admin_edited_description():
    # An admin-renamed description is not the auto-generated form -> keep it;
    # still heal the bogus memory.
    out = gpu_card_metadata_resync(
        {"memory": "0 GB", "description": "Lab card 3 (do not touch)"},
        {"memory_total_mb": 97280, "name": _CLEAN},
    )
    assert out == {"memory": "95 GB"}


def test_resync_noop_when_card_still_vfio_bound():
    # No NVML reading yet (fresh memory 0) -> nothing to heal, no churn.
    out = gpu_card_metadata_resync(
        {"memory": "0 GB", "description": _FALLBACK_DESC},
        {"memory_total_mb": 0, "name": _CLEAN},
    )
    assert out == {}
