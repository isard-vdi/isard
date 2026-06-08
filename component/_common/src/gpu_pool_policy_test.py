"""Unit tests for the shared vGPU reconcile policy.

Imported directly (path-inserted) so it runs without needing the
``isardvdi_common`` package name on the path. The engine's existing
``_gpu_pool_test.py`` covers ``decide_reconcile_action`` via its re-export;
this file pins the canonicalization helpers and the canonicalize-inside
realizability fix that lives only in the shared module.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import gpu_pool_policy as gpp  # noqa: E402


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
