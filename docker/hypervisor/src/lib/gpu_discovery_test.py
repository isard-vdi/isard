"""Unit tests for gpu_discovery._classify_sriov_state.

Run locally (no CI pytest gate for the hypervisor lib):
    cd docker/hypervisor/src/lib && python -m pytest gpu_discovery_test.py -v

The module is not packaged, so add its own directory to sys.path before
importing (mirrors how the lib is loaded inside the hypervisor container).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from gpu_discovery import _classify_sriov_state, normalize_gpu_model


@pytest.mark.parametrize(
    "totalvfs, numvfs, has_profiles, vf_driver, expect_note, expect_warning",
    [
        # Not SR-IOV capable at all (e.g. consumer card / pure passthrough
        # board): nothing to say. Clean UI.
        (0, 0, False, "", False, False),
        (0, 0, True, "", False, False),
        # SR-IOV capable, no VFs, no profiles: the correct steady state for
        # a Blackwell DC board serving passthrough/MIG. One neutral note,
        # NO warning -> admin UI stays clean when everything is correct.
        (16, 0, False, "", True, False),
        (32, 0, False, "", True, False),
        # SR-IOV capable WITH vGPU profiles present (normal A40-style vGPU
        # card): not our concern regardless of VF count -> no note/warning.
        (16, 0, True, "", False, False),
        (16, 16, True, "nvidia", False, False),
        (16, 8, True, "vfio-pci", False, False),
        # VFs created but no profiles and VFs not nvidia-bound: genuine
        # IOMMU/driver misconfiguration -> warning, no note.
        (16, 16, False, "vfio-pci", False, True),
        (16, 4, False, "", False, True),
        # VFs created, nvidia-bound, but still no profiles: genuine
        # unexpected state -> warning, no note.
        (16, 16, False, "nvidia", False, True),
    ],
)
def test_classify_sriov_state(
    totalvfs, numvfs, has_profiles, vf_driver, expect_note, expect_warning
):
    notes, warnings = _classify_sriov_state(totalvfs, numvfs, has_profiles, vf_driver)
    assert bool(notes) is expect_note
    assert bool(warnings) is expect_warning
    # A card is never simultaneously "fine (note)" and "broken (warning)".
    assert not (notes and warnings)


def test_note_text_is_reassuring_not_a_fault():
    """The passthrough/MIG steady-state message must read as expected,
    not as a failure (it used to be a 'VF creation failed' warning)."""
    notes, warnings = _classify_sriov_state(24, 0, False, "")
    assert warnings == []
    assert len(notes) == 1
    msg = notes[0]
    assert "expected" in msg
    assert "passthrough/MIG" in msg
    assert "24 VFs supported" in msg
    assert "fail" not in msg.lower()


def test_iommu_warning_names_the_bound_driver():
    notes, warnings = _classify_sriov_state(16, 16, False, "vfio-pci")
    assert notes == []
    assert len(warnings) == 1
    assert "driver=vfio-pci" in warnings[0]
    assert "iommu=pt" in warnings[0]


def test_iommu_warning_handles_unknown_driver():
    notes, warnings = _classify_sriov_state(16, 16, False, "")
    assert notes == []
    assert "driver=none" in warnings[0]


# normalize_gpu_model output is used verbatim as a URL path segment inside the
# BRAND-MODEL-PROFILE reservable id, so it must be space-, dash- AND slash-free.
# The A16 die's PCI name "GA107GL [A2 / A16]" is the regression that motivated
# slash stripping: a '/' made the reservables enable route 405.
@pytest.mark.parametrize(
    "gpu_name, expected",
    [
        ("NVIDIA A16", "A16"),
        ("NVIDIA RTX A6000", "RTXA6000"),
        ("NVIDIA GA107GL [A2 / A16]", "GA107GL[A2A16]"),
        ("GA107GL[A2/A16]", "GA107GL[A2A16]"),
    ],
)
def test_normalize_gpu_model_name_path_is_clean(gpu_name, expected):
    result = normalize_gpu_model(gpu_name)
    assert result == expected
    assert "/" not in result
    assert "-" not in result
    assert " " not in result


@pytest.mark.parametrize(
    "profile_name, expected",
    [
        ("A16-2Q", "A16"),
        ("A100-1-5C", "A100"),
        ("GA107GL[A2/A16]-2Q", "GA107GL[A2A16]"),
    ],
)
def test_normalize_gpu_model_profile_path_is_clean(profile_name, expected):
    result = normalize_gpu_model("irrelevant", vgpu_profiles=[{"name": profile_name}])
    assert result == expected
    assert "/" not in result
