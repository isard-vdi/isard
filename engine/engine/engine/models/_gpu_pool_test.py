import pytest

from engine.models._gpu_pool import (
    _profile_pool_size,
    decide_reconcile_action,
    plan_passthrough_dedup,
    plan_pool_trim,
)

# ---- decide_reconcile_action -------------------------------------------------

# Common discovery shapes used by reconcile-decision tests.
_A16_TYPES = {
    "1Q": {"id": "nvidia-711", "max": 16, "available": 16, "memory": 1024},
    "2Q": {"id": "nvidia-712", "max": 8, "available": 16, "memory": 2048},
    "4Q": {"id": "nvidia-713", "max": 4, "available": 16, "memory": 4096},
    "passthrough": {"id": "passthrough", "max": 1, "available": 1, "memory": 15356},
}
_PASSTHROUGH_ONLY = {
    "passthrough": {"id": "passthrough", "max": 1, "available": 1, "memory": 15356},
}


def test_apply_when_requested_profile_visible():
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="2Q",
    )
    assert d == {"action": "apply", "profile": "2Q"}


def test_apply_uses_scheduled_over_requested():
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile="4Q",
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="2Q",
    )
    assert d == {"action": "apply", "profile": "4Q"}


def test_skip_retry_when_discovery_empty_on_sriov_card():
    """The bug we are fixing: hypervisor reports empty types post-restart, but
    the operator's 2Q is still the desired state. Reconcile must skip and
    flag retryable so the engine's bounded retry loop re-runs once the
    hypervisor's settle helpers succeed."""
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile=None,
        available_types={},
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default=None,
    )
    assert d == {
        "action": "skip_retry",
        "reason": "discovery_incomplete",
        "profile": "2Q",
    }


def test_skip_retry_when_only_passthrough_on_sriov_card():
    """Same shape: types collapsed to passthrough-only (engine's existing
    'no vgpu_profiles' branch) on an SR-IOV card is the cascade trigger.
    Treat as discovery-incomplete, not as 'operator chose passthrough'."""
    d = decide_reconcile_action(
        requested_profile="4Q",
        scheduled_profile=None,
        available_types=_PASSTHROUGH_ONLY,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="4Q",
    )
    assert d["action"] == "skip_retry"
    assert d["profile"] == "4Q"


def test_skip_fault_when_requested_genuinely_unavailable():
    """The hardware shows real types but not the operator's requested one.
    Surface a fault for the webui; never auto-fall-back to a different
    profile (that would mutate operator intent)."""
    d = decide_reconcile_action(
        requested_profile="48Q",  # A40-only profile, not in A16 types
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="2Q",
    )
    assert d == {
        "action": "skip_fault",
        "reason": "requested_profile_unavailable",
        "profile": "48Q",
    }


def test_seed_and_apply_on_first_discovery():
    """No requested_profile in DB (fresh GPU). Caller must write the
    fallback_default into requested_profile before applying."""
    d = decide_reconcile_action(
        requested_profile=None,
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="2Q",
    )
    assert d == {"action": "seed_and_apply", "profile": "2Q"}


def test_seed_and_apply_uses_fallback_default_for_passthrough_only_card():
    """Non-SR-IOV passthrough-only card: types is {'passthrough': ...},
    sriov_totalvfs=0. Should seed 'passthrough' as the operator default."""
    d = decide_reconcile_action(
        requested_profile=None,
        scheduled_profile=None,
        available_types=_PASSTHROUGH_ONLY,
        sriov_totalvfs=0,
        operator_passthrough=False,
        fallback_default="passthrough",
    )
    assert d == {"action": "seed_and_apply", "profile": "passthrough"}


# hyp.py now passes fallback_default="passthrough" for a card with no planning
# and no operator intent (instead of the max vGPU profile). These tests pin
# that contract: an unconfigured card defaults to passthrough even when vGPU
# types ARE available, while a card with a planning or prior intent is never
# clobbered to passthrough on a degraded/empty discovery.
def test_unconfigured_card_defaults_to_passthrough_even_with_vgpu_types():
    """No planning + no requested + vGPU types present: still seed
    passthrough (whole GPU), NOT the max vGPU profile."""
    d = decide_reconcile_action(
        requested_profile=None,
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="passthrough",
    )
    assert d == {"action": "seed_and_apply", "profile": "passthrough"}


def test_active_planning_not_clobbered_to_passthrough_when_types_degraded():
    """A scheduled (booked) profile must NOT be downgraded to passthrough when
    discovery degraded to passthrough-only (e.g. vGPU manager down): preserve
    and retry."""
    d = decide_reconcile_action(
        requested_profile=None,
        scheduled_profile="4Q",
        available_types=_PASSTHROUGH_ONLY,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="passthrough",
    )
    assert d["action"] == "skip_retry"
    assert d["profile"] == "4Q"


def test_prior_requested_profile_not_clobbered_to_passthrough_when_types_degraded():
    """A prior operator profile must survive a degraded discovery, not flip to
    the passthrough default."""
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile=None,
        available_types=_PASSTHROUGH_ONLY,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="passthrough",
    )
    assert d["action"] == "skip_retry"
    assert d["profile"] == "2Q"


def test_skip_noop_when_no_default_resolvable():
    d = decide_reconcile_action(
        requested_profile=None,
        scheduled_profile=None,
        available_types={},
        sriov_totalvfs=0,
        operator_passthrough=False,
        fallback_default=None,
    )
    assert d == {"action": "skip_noop", "reason": "no_profile_resolvable"}


def test_refuse_passthrough_without_operator_flag():
    """If the operator did not explicitly set passthrough but somehow the
    effective profile resolved to 'passthrough' (e.g. stale DB from the
    legacy bug), reconcile must refuse to rebind vfio-pci."""
    d = decide_reconcile_action(
        requested_profile="passthrough",
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="2Q",
    )
    assert d == {
        "action": "refuse_passthrough",
        "reason": "operator_passthrough_not_set",
    }


def test_apply_passthrough_when_operator_flag_set():
    """Operator explicitly chose passthrough — the rebind is legitimate."""
    d = decide_reconcile_action(
        requested_profile="passthrough",
        scheduled_profile=None,
        available_types=_A16_TYPES,
        sriov_totalvfs=16,
        operator_passthrough=True,
        fallback_default="passthrough",
    )
    assert d == {"action": "apply", "profile": "passthrough"}


def test_non_sriov_card_with_empty_types_is_skip_fault_not_retry():
    """A non-SR-IOV card with empty types is a genuine failure, not a
    transient discovery race. Should surface a fault, not retry forever."""
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile=None,
        available_types={},
        sriov_totalvfs=0,  # NOT SR-IOV
        operator_passthrough=False,
        fallback_default=None,
    )
    assert d["action"] == "skip_fault"


def test_regression_cascade_input_does_not_call_passthrough():
    """The exact production cascade we are fixing: vgpu_profile == '2Q' in
    DB, hypervisor reported empty profiles for the umpteenth time post-
    upgrade, available_types collapsed to {'passthrough': ...}. The OLD
    behavior would fall back to passthrough and call change_vgpu_profile
    which rebinds vfio-pci. The new decision must skip and request retry,
    NEVER produce 'apply passthrough'."""
    d = decide_reconcile_action(
        requested_profile="2Q",
        scheduled_profile=None,
        available_types=_PASSTHROUGH_ONLY,
        sriov_totalvfs=16,
        operator_passthrough=False,
        fallback_default="passthrough",  # the legacy buggy fallback
    )
    assert d["action"] == "skip_retry"
    assert d["profile"] == "2Q"
    # The negative assertion is the whole point of this test:
    assert d["action"] != "apply"
    assert d.get("profile") != "passthrough"


def _e(created=False, started=False, reserved=False, pci="0000:05:00.0"):
    return {
        "created": created,
        "domain_started": started,
        "domain_reserved": reserved,
        "pci_mdev_id": pci,
        "type_id": "t",
    }


@pytest.mark.parametrize(
    "d_type, expected",
    [
        # SR-IOV: `available` counts free VFs and overshoots `max` -> use max
        ({"max": 4, "available": 16}, 4),
        ({"max": 8, "available": 2}, 8),
        # `max` None (e.g. some A40 firmware) -> fall back to available
        ({"max": None, "available": 6}, 6),
        # `max` 0 / negative -> fall back to available
        ({"max": 0, "available": 5}, 5),
        ({"max": -1, "available": 3}, 3),
        # `max` missing entirely -> fall back to available
        ({"available": 7}, 7),
        # nothing usable -> floor at 1
        ({"max": None}, 1),
        ({}, 1),
        ({"max": None, "available": 0}, 1),
        # bool guard: True/False must NOT be treated as int 1/0
        ({"max": True, "available": 9}, 9),
        ({"max": False, "available": 9}, 9),
        # MIG profile: same contract, max wins
        ({"max": 7, "available": 99, "mig": True, "mig_profile_id": "1g.10gb"}, 7),
        ({"max": None, "available": 2, "mig": True}, 2),
        # defensive coercion of non-int `available`
        ({"max": None, "available": "4"}, 4),
        ({"max": None, "available": "garbage"}, 1),
        ({"max": None, "available": None}, 1),
    ],
)
def test_profile_pool_size(d_type, expected):
    assert _profile_pool_size(dict(d_type)) == expected


def test_profile_pool_size_does_not_mutate_input():
    d = {"max": None, "available": 6}
    _profile_pool_size(d)
    assert d == {"max": None, "available": 6}


# --- plan_pool_trim -------------------------------------------------------


def test_trim_noop_when_within_cap():
    assert plan_pool_trim({"a": _e(), "b": _e()}, 2) is None
    assert plan_pool_trim({"a": _e()}, 4) is None


def test_trim_noop_on_bad_cap():
    assert plan_pool_trim({"a": _e(), "b": _e()}, 0) is None
    assert plan_pool_trim({"a": _e(), "b": _e()}, None) is None


def test_trim_all_free_down_to_cap():
    pool = {f"u{i}": _e() for i in range(16)}
    kept, removed = plan_pool_trim(pool, 4)
    assert len(kept) == 4
    assert len(removed) == 12
    assert set(kept) | set(removed) == set(pool)


def test_trim_keeps_all_in_use_and_fills_with_free():
    pool = {
        "run": _e(started="dom-1"),
        "res": _e(reserved="dom-2"),
        "made": _e(created=True),
        "free1": _e(),
        "free2": _e(),
    }
    kept, removed = plan_pool_trim(pool, 4)
    assert {"run", "res", "made"}.issubset(kept)  # never drop in-use
    assert len(kept) == 4
    assert len(removed) == 1
    assert removed[0] in ("free1", "free2")


def test_trim_needs_review_when_inuse_exceeds_cap():
    # 3 in-use but cap 1 -> cannot reach cap safely -> leave intact
    pool = {
        "a": _e(started="d1"),
        "b": _e(started="d2"),
        "c": _e(created=True),
    }
    assert plan_pool_trim(pool, 1) is None


def test_trim_is_deterministic_idempotent():
    pool = {f"u{i}": _e() for i in range(10)}
    first = plan_pool_trim(pool, 3)[0]
    # re-running on the kept set is a no-op (already at cap)
    assert plan_pool_trim(first, 3) is None


def test_trim_treats_domain_bound_uuid_as_in_use():
    # entry looks free by flags but a (Stopped/reserved) domain still
    # references it via vgpu_info -> must never be trimmed.
    pool = {"bound": _e(), "f1": _e(), "f2": _e(), "f3": _e()}
    kept, removed = plan_pool_trim(pool, 2, bound_uuids={"bound"})
    assert "bound" in kept
    assert "bound" not in removed
    assert len(kept) == 2


def test_trim_needs_review_when_bound_count_exceeds_cap():
    pool = {"b1": _e(), "b2": _e(), "f1": _e()}
    assert plan_pool_trim(pool, 1, bound_uuids={"b1", "b2"}) is None


# --- plan_passthrough_dedup ----------------------------------------------


def test_passthrough_dedup_noop_single():
    assert plan_passthrough_dedup({"a": _e(pci="0000:63:00.0")}) is None
    assert plan_passthrough_dedup({}) is None


def test_passthrough_dedup_prefers_canonical():
    pool = {
        "legacy": _e(created=True, pci="pci_0000_63_00_0"),
        "canon": _e(created=True, pci="0000:63:00.0"),
    }
    kept, removed = plan_passthrough_dedup(pool)
    assert list(kept) == ["canon"]
    assert removed == ["legacy"]


def test_passthrough_dedup_triple():
    pool = {
        "l1": _e(created=True, pci="pci_0000_86_00_0"),
        "c": _e(created=True, pci="0000:86:00.0"),
        "l2": _e(created=True, pci="pci_0000_86_00_0"),
    }
    kept, removed = plan_passthrough_dedup(pool)
    assert list(kept) == ["c"]
    assert sorted(removed) == ["l1", "l2"]


def test_passthrough_dedup_skips_when_bound():
    pool = {
        "a": _e(created=True, started="dom-9", pci="pci_0000_63_00_0"),
        "b": _e(created=True, pci="0000:63:00.0"),
    }
    assert plan_passthrough_dedup(pool) is None


def test_passthrough_dedup_no_canonical_keeps_first_sorted():
    pool = {
        "z": _e(created=True, pci="pci_0000_63_00_0"),
        "a": _e(created=True, pci="pci_0000_63_00_0"),
    }
    kept, removed = plan_passthrough_dedup(pool)
    assert list(kept) == ["a"]
    assert removed == ["z"]


def test_passthrough_dedup_skips_when_bound_by_domain():
    # neither entry flagged started/reserved, but a domain's vgpu_info
    # still references one -> do not dedup (conservative).
    pool = {
        "legacy": _e(created=True, pci="pci_0000_63_00_0"),
        "canon": _e(created=True, pci="0000:63:00.0"),
    }
    assert plan_passthrough_dedup(pool, bound_uuids={"canon"}) is None
