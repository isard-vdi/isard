import pytest
from engine.models._gpu_pool import (
    _profile_pool_size,
    plan_passthrough_dedup,
    plan_pool_trim,
)


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
