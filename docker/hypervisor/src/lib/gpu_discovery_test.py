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
from gpu_discovery import _classify_sriov_state


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
