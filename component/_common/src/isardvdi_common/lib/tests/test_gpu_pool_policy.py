"""Unit tests for the shared vGPU reconcile policy.

The engine's existing
``_gpu_pool_test.py`` covers ``decide_reconcile_action`` via its re-export;
this file pins the canonicalization helpers and the canonicalize-inside
realizability fix that lives only in the shared module.
"""

import pytest
from isardvdi_common.lib import gpu_pool_policy as gpp


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("4Q", "4Q"),
        ("1C", "1C"),
        ("passthrough", "passthrough"),
        ("1g.24gb", "1g.24gb"),  # MIG dot-form untouched
        ("1-2Q", "1_2Q"),  # MIG dash-form -> underscore
        ("  4Q  ", "4Q"),
        (None, None),
    ],
)
def test_canonical_suffix(raw, expected):
    assert gpp.canonical_suffix(raw) == expected


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("NVIDIA-A16-4Q", "NVIDIA-A16-4Q"),
        ("NVIDIA-A100-1-2Q", "NVIDIA-A100-1_2Q"),
        ("NVIDIA-A16-passthrough", "NVIDIA-A16-passthrough"),
    ],
)
def test_canonical_profile_id(rid, expected):
    assert gpp.canonical_profile_id(rid) == expected


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("NVIDIA-A16-2Q", "2Q"),  # full id -> suffix
        ("NVIDIA-A100-1-2Q", "1_2Q"),  # dash-form MIG full id -> canonical suffix
        ("NVIDIA-A16-1g.24gb", "1g.24gb"),  # dot-form MIG untouched
        ("NVIDIA-A16-passthrough", "passthrough"),
        ("2Q", "2Q"),  # bare suffix passes through
        ("1_2Q", "1_2Q"),  # bare canonical MIG suffix
        ("1-2Q", "1_2Q"),  # bare dash-form suffix still canonicalized
        ("passthrough", "passthrough"),
        (False, False),  # falsy / non-str passes through
    ],
)
def test_profile_suffix_from_id(rid, expected):
    assert gpp.profile_suffix_from_id(rid) == expected


def _decide(**kw):
    base = dict(
        requested_profile=None,
        scheduled_profile=None,
        available_types={"4Q": {}, "passthrough": {}},
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="passthrough",
    )
    base.update(kw)
    return gpp.decide_reconcile_action(**base)


def test_dash_form_mig_scheduled_matches_underscore_key():
    # The canonicalize-inside fix: a dash-form MIG scheduled profile must NOT be
    # misclassified skip_fault against an underscore-form driver key.
    d = _decide(
        scheduled_profile="1-2Q", available_types={"1_2Q": {}, "passthrough": {}}
    )
    assert d["action"] == "apply"


def test_genuinely_unavailable_is_skip_fault():
    d = _decide(requested_profile="4C")
    assert d["action"] == "skip_fault"


def test_unconfigured_seeds_passthrough():
    d = _decide()
    assert d == {"action": "seed_and_apply", "profile": "passthrough"}


def test_sriov_only_passthrough_is_skip_retry():
    d = _decide(scheduled_profile="4Q", available_types={"passthrough": {}})
    assert d["action"] == "skip_retry"


def test_passthrough_without_operator_flag_refused():
    d = _decide(requested_profile="passthrough", available_types={"passthrough": {}})
    assert d["action"] == "refuse_passthrough"


def test_scheduled_passthrough_applies_without_operator_flag():
    # Calendar is king: a passthrough that the planning calendar schedules for
    # this card applies even when operator_passthrough is False -- the planning
    # IS the opt-in for the (destructive) vfio-pci rebind. Covers a card that
    # exposes both vGPU and passthrough types, has no operator flag, and has a
    # current passthrough planning.
    d = _decide(scheduled_profile="passthrough")
    assert d == {"action": "apply", "profile": "passthrough"}


def test_valid_scheduled_applies():
    d = _decide(scheduled_profile="4Q")
    assert d == {"action": "apply", "profile": "4Q"}


def test_keep_current_applies_without_seed():
    # Registration with a live carve as fallback and keep_current=True: apply it
    # but DO NOT seed requested_profile (ephemeral).
    d = _decide(fallback_default="4Q", keep_current=True)
    assert d == {"action": "keep_current", "profile": "4Q"}


def test_keep_current_false_still_seeds():
    # The engine reconcile call site passes no keep_current -> unchanged seed.
    d = _decide(fallback_default="4Q")
    assert d == {"action": "seed_and_apply", "profile": "4Q"}


def test_booking_overrides_keep_current():
    d = _decide(scheduled_profile="4Q", fallback_default="1C", keep_current=True)
    assert d == {"action": "apply", "profile": "4Q"}


def test_requested_overrides_keep_current():
    d = _decide(requested_profile="4Q", fallback_default="1C", keep_current=True)
    assert d == {"action": "apply", "profile": "4Q"}


# --- variant qualifier (@<name>) --------------------------------------------


@pytest.mark.parametrize(
    "rid,base,name",
    [
        ("NVIDIA-L40S-8Q", "NVIDIA-L40S-8Q", None),
        ("NVIDIA-L40S-8Q~lab", "NVIDIA-L40S-8Q", "lab"),
        ("NVIDIA-A16-1-2Q~x", "NVIDIA-A16-1-2Q", "x"),
        (None, None, None),
    ],
)
def test_split_qualifier(rid, base, name):
    assert gpp.split_qualifier(rid) == (base, name)


@pytest.mark.parametrize(
    "rid,expected",
    [
        ("NVIDIA-L40S-8Q~lab", "8Q"),  # ~<name> stripped -> matches info.types key
        ("NVIDIA-RTXPro6000DC-1g.24gb~prod", "1g.24gb"),
        ("NVIDIA-A16-1-2Q~x", "1_2Q"),  # dash-form canonicalized + @ stripped
        ("NVIDIA-L40S-8Q", "8Q"),
        ("8Q", "8Q"),  # already-bare suffix passes through
    ],
)
def test_profile_suffix_from_id_strips_variant(rid, expected):
    assert gpp.profile_suffix_from_id(rid) == expected


def test_canonical_profile_id_preserves_variant():
    assert gpp.canonical_profile_id("NVIDIA-A16-1-2Q~lab") == "NVIDIA-A16-1_2Q~lab"
    assert gpp.canonical_profile_id("NVIDIA-L40S-8Q~lab") == "NVIDIA-L40S-8Q~lab"


# --- the scheduler same-profile NO-OP contract ------------------------------
# scheduler/.../actions.py gpu_profile_set skips the engine call (a hardware
# no-op: no re-carve, no quiesce) when the card's live profile already equals
# the plan's target, i.e. when
#   canonical_suffix(vgpus.vgpu_profile) == profile_suffix_from_id(subitem_id)
# These cases pin that equality so a same-profile plan boundary never churns a
# physical card; only the booking END stops desktops.


@pytest.mark.parametrize(
    "live_profile,subitem_id",
    [
        ("passthrough", "NVIDIA-GB203GL[RTXPRO4000Blackwell]-passthrough"),
        ("8Q", "NVIDIA-RTXPro6000BlackwellDC-8Q"),
        ("1_2Q", "NVIDIA-A100-1-2Q"),  # live underscore vs plan dash-form MIG
        ("1_2Q", "NVIDIA-A100-1_2Q"),
        ("8Q", "NVIDIA-L40S-8Q~lab"),  # a ~variant plan still no-ops the bare card
    ],
)
def test_same_profile_is_a_noop(live_profile, subitem_id):
    assert gpp.canonical_suffix(live_profile) == gpp.profile_suffix_from_id(subitem_id)


@pytest.mark.parametrize(
    "live_profile,subitem_id",
    [
        ("passthrough", "NVIDIA-RTXPro6000BlackwellDC-8Q"),  # PT card -> vGPU plan
        ("8Q", "NVIDIA-RTXPro6000BlackwellDC-1_24Q"),  # different vGPU carve
        ("8Q", "NVIDIA-RTXPro6000BlackwellDC-passthrough"),  # vGPU -> passthrough
        ("1_2Q", "NVIDIA-A100-2_4Q"),  # different MIG slice
    ],
)
def test_different_profile_is_not_a_noop(live_profile, subitem_id):
    assert gpp.canonical_suffix(live_profile) != gpp.profile_suffix_from_id(subitem_id)


def test_operator_passthrough_overrides_keep_current():
    # A card the operator forced to passthrough, but discovered as a realizable
    # SR-IOV carve (so keep_current=True) -- e.g. after a reboot where idle-reclaim
    # + discovery re-cycled it -- must be reverted to passthrough, NOT kept on the
    # incidental carve. The durable operator_passthrough intent is authoritative.
    d = _decide(operator_passthrough=True, fallback_default="4Q", keep_current=True)
    assert d == {"action": "seed_and_apply", "profile": "passthrough"}


def test_booking_still_overrides_operator_passthrough():
    # A live scheduled booking outranks the operator's standing passthrough force.
    d = _decide(
        scheduled_profile="4Q",
        operator_passthrough=True,
        fallback_default="passthrough",
        keep_current=True,
    )
    assert d == {"action": "apply", "profile": "4Q"}
