"""Unit tests for the pure vGPU realizability/prune decision logic.

``gpu_realizability`` is a dependency-free leaf module under
``isardvdi_common.lib.bookings`` (port of upstream MR !4496/!4519
api/src/api/libv2/gpu_realizability.py).
"""

import pytest
from isardvdi_common.lib.bookings import gpu_realizability as gr

# --- canonicalization --------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("4Q", "4Q"),
        ("1C", "1C"),
        ("passthrough", "passthrough"),
        ("1g.24gb", "1g.24gb"),  # MIG dot-form untouched
        ("1-2Q", "1_2Q"),  # MIG dash-form -> underscore
        ("2-4C", "2_4C"),
        ("  4Q  ", "4Q"),
        (None, None),
    ],
)
def test_canonical_suffix(raw, expected):
    assert gr.canonical_suffix(raw) == expected


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("NVIDIA-A16-4Q", "NVIDIA-A16-4Q"),
        ("NVIDIA-A16-1-2Q", "NVIDIA-A16-1_2Q"),  # dash-form MIG suffix
        ("NVIDIA-RTXPro6000BlackwellDC-1-4Q", "NVIDIA-RTXPro6000BlackwellDC-1_4Q"),
        ("NVIDIA-A16-passthrough", "NVIDIA-A16-passthrough"),
    ],
)
def test_canonical_profile_id(rid, expected):
    assert gr.canonical_profile_id(rid) == expected


# --- realizable_suffixes -----------------------------------------------------


def _vgpu(*suffixes):
    return [{"name": f"A16-{s}"} for s in suffixes]


def test_realizable_suffixes_none_on_discovery_failed():
    # vgpu_profiles=None is the DISCOVERY_FAILED sentinel -> never drives prune
    assert gr.realizable_suffixes({"vgpu_profiles": None}) is None


def test_realizable_suffixes_real_reading_includes_passthrough():
    got = gr.realizable_suffixes({"vgpu_profiles": _vgpu("1Q", "2Q", "4Q")})
    assert got == {"passthrough", "1Q", "2Q", "4Q"}


def test_realizable_suffixes_empty_list_is_passthrough_only():
    # [] (not None) == genuinely no vGPU types (compute/passthrough-only board)
    assert gr.realizable_suffixes({"vgpu_profiles": []}) == {"passthrough"}


def test_realizable_suffixes_mig():
    got = gr.realizable_suffixes(
        {"vgpu_profiles": [], "mig_profiles": [{"name": "1g.24gb"}, {"name": "2-4C"}]}
    )
    assert got == {"passthrough", "1g.24gb", "2_4C"}


# --- reading_trustworthy (the safety-critical gate) --------------------------


def test_trustworthy_false_on_discovery_failed():
    assert gr.reading_trustworthy({"vgpu_profiles": None}, 16) is False


def test_trustworthy_false_sriov_card_only_passthrough():
    # SR-IOV-capable card reporting only passthrough this cycle == degraded /
    # vgpud-down / half-initialized -> NEVER prune
    assert gr.reading_trustworthy({"vgpu_profiles": []}, 16) is False


def test_trustworthy_true_sriov_card_with_vgpu_types():
    assert gr.reading_trustworthy({"vgpu_profiles": _vgpu("4Q")}, 16) is True


def test_trustworthy_true_non_sriov_passthrough_only_card():
    # genuine passthrough-only board is non-SR-IOV -> trusted
    assert gr.reading_trustworthy({"vgpu_profiles": []}, 0) is True


def test_trustworthy_true_mig_card_only():
    assert (
        gr.reading_trustworthy(
            {"vgpu_profiles": [], "mig_profiles": [{"name": "1g.24gb"}]}, 16
        )
        is True
    )


# --- plan_card_prunes --------------------------------------------------------


def test_prune_only_the_unrealizable_enabled_profile():
    # Card realizes Q-series; 4C is enabled but unrealizable -> prune ONLY 4C
    cards = [
        {
            "id": "h-pci_0000_c6_00_0",
            "profiles_enabled": ["NVIDIA-A16-2Q", "NVIDIA-A16-4C", "NVIDIA-A16-4Q"],
            "gpu_payload": {"vgpu_profiles": _vgpu("1Q", "2Q", "4Q", "8Q", "16Q")},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == [
        ("h-pci_0000_c6_00_0", "NVIDIA-A16-4C")
    ]


def test_no_prune_when_card_not_read_this_cycle():
    cards = [
        {
            "id": "h-c6",
            "profiles_enabled": ["NVIDIA-A16-4C"],
            "gpu_payload": None,  # not in this POST
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == []


def test_no_prune_when_reading_degraded():
    # SR-IOV card reporting only passthrough -> untrustworthy -> preserve 4C
    cards = [
        {
            "id": "h-c6",
            "profiles_enabled": ["NVIDIA-A16-4C", "NVIDIA-A16-4Q"],
            "gpu_payload": {"vgpu_profiles": []},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == []


def test_mixed_driver_only_unrealizing_card_pruned():
    # Server A realizes 4C, server B does not -> only B's enable is dropped;
    # A keeps it, so the reservable survives (handled by the orchestration).
    cards = [
        {
            "id": "hA-card",
            "profiles_enabled": ["NVIDIA-A16-4C", "NVIDIA-A16-4Q"],
            "gpu_payload": {"vgpu_profiles": _vgpu("4Q", "4C")},
            "sriov_totalvfs": 16,
        },
        {
            "id": "hB-card",
            "profiles_enabled": ["NVIDIA-A16-4C", "NVIDIA-A16-4Q"],
            "gpu_payload": {"vgpu_profiles": _vgpu("4Q")},
            "sriov_totalvfs": 16,
        },
    ]
    assert gr.plan_card_prunes("A16", cards) == [("hB-card", "NVIDIA-A16-4C")]


def test_no_prune_variant_passthrough_always_realizable():
    # A "~<variant>" passthrough is always realizable (the variant is only an admin
    # label); it must NEVER be pruned on a re-registration. Regression: the full
    # variant id was compared against a BARE realizable set and wrongly pruned,
    # wiping every variant profile on each hypervisor restart.
    cards = [
        {
            "id": "h-c6",
            "profiles_enabled": ["NVIDIA-A16-passthrough~lab"],
            "gpu_payload": {"vgpu_profiles": _vgpu("1Q", "2Q", "4Q")},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == []


def test_prune_variant_when_bare_profile_unrealizable():
    # The BARE profile drives realizability; an unrealizable bare profile IS still
    # pruned -- by its FULL "~<variant>" id, so enable_subitem disables the right
    # entry.
    cards = [
        {
            "id": "h-c6",
            "profiles_enabled": ["NVIDIA-A16-4C~lab"],
            "gpu_payload": {"vgpu_profiles": _vgpu("1Q", "2Q", "4Q")},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == [("h-c6", "NVIDIA-A16-4C~lab")]


def test_no_prune_variant_dashed_mig_suffix():
    # A dashed-MIG variant ("1-2Q~lab") reduces (base, canonical) to NVIDIA-A16-1_2Q
    # which the MIG reading realizes -> no prune (stripping the variant AND the
    # dash-form both matter).
    cards = [
        {
            "id": "h-c6",
            "profiles_enabled": ["NVIDIA-A16-1-2Q~lab"],
            "gpu_payload": {"vgpu_profiles": [], "mig_profiles": [{"name": "1-2Q"}]},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == []


def test_other_model_ids_untouched():
    cards = [
        {
            "id": "h-card",
            "profiles_enabled": ["NVIDIA-A40-4C", "NVIDIA-A16-4C"],
            "gpu_payload": {"vgpu_profiles": _vgpu("4Q")},
            "sriov_totalvfs": 16,
        }
    ]
    # Only the A16 id is considered for model "A16"; the A40 id is left alone.
    assert gr.plan_card_prunes("A16", cards) == [("h-card", "NVIDIA-A16-4C")]


def test_dash_form_mig_realizable_not_pruned():
    # Reservable stored dash-form, info reports underscore-form -> canonical
    # match -> NOT pruned (guards the dash-form MIG install).
    cards = [
        {
            "id": "h-card",
            "profiles_enabled": ["NVIDIA-A16-1-2Q"],
            "gpu_payload": {"vgpu_profiles": [], "mig_profiles": [{"name": "1_2Q"}]},
            "sriov_totalvfs": 16,
        }
    ]
    assert gr.plan_card_prunes("A16", cards) == []


# --- variant qualifier (@<name>) --------------------------------------------


@pytest.mark.parametrize(
    "rid,base,name",
    [
        ("NVIDIA-L40S-8Q", "NVIDIA-L40S-8Q", None),
        ("NVIDIA-L40S-8Q~lab", "NVIDIA-L40S-8Q", "lab"),
        ("NVIDIA-RTXPro6000DC-1g.24gb~prod", "NVIDIA-RTXPro6000DC-1g.24gb", "prod"),
        ("NVIDIA-A16-1-2Q~x", "NVIDIA-A16-1-2Q", "x"),
        ("passthrough", "passthrough", None),
        (None, None, None),
    ],
)
def test_split_qualifier(rid, base, name):
    assert gr.split_qualifier(rid) == (base, name)


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("NVIDIA-L40S-8Q~lab", "8Q"),
        ("NVIDIA-L40S-8Q", "8Q"),
        (
            "NVIDIA-RTXPro6000DC-1g.24gb~prod",
            "1g.24gb",
        ),  # dot-form MIG kept, @ stripped
        ("NVIDIA-A16-1-2Q~x", "1_2Q"),  # dash-form MIG canonicalized, @ stripped
        ("NVIDIA-A16-1-2Q", "1_2Q"),
        ("NVIDIA-T4-passthrough~p", "passthrough"),
    ],
)
def test_bare_suffix(rid, expected):
    assert gr.bare_suffix(rid) == expected


@pytest.mark.parametrize(
    "rid,expected",
    [
        # canonical_profile_id canonicalizes the suffix while preserving ~<name>
        ("NVIDIA-A16-1-2Q~lab", "NVIDIA-A16-1_2Q~lab"),
        ("NVIDIA-L40S-8Q~lab", "NVIDIA-L40S-8Q~lab"),
        ("NVIDIA-L40S-8Q", "NVIDIA-L40S-8Q"),
    ],
)
def test_canonical_profile_id_preserves_variant(rid, expected):
    assert gr.canonical_profile_id(rid) == expected
