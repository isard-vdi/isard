"""Unit tests for the v189 vGPU model-token unification helpers.

The canon/unify helpers live in ``upgrade_helpers.py``, which keeps `re` as its
only hard module-level dependency precisely so this suite can load it directly
(``upgrade.py`` itself cannot be imported bare: humanfriendly, rethinkdb,
config). These pure helpers are the heart of the migration; the DB cascade
around them is exercised in staging.
"""

import os
import runpy
import types

import pytest


def _load_helpers():
    ns = runpy.run_path(
        os.path.join(os.path.dirname(__file__), "upgrade_helpers.py"),
        run_name="_vgpu_unify_under_test",
    )
    return types.SimpleNamespace(**ns)


m = _load_helpers()


# --- _unify_model: stored MODEL string -> canonical survivor ----------------
@pytest.mark.parametrize(
    "stored, expected",
    [
        # Blackwell RTX PRO 6000 (device 10de:2bb5): all three discovery-path
        # tokens collapse to the vGPU-profile-derived canonical.
        ("RTXPro6000BlackwellDC", "RTXPro6000BlackwellDC"),
        ("RTXPRO6000BlackwellServerEdition", "RTXPro6000BlackwellDC"),
        ("GB202GL[RTXPRO6000BlackwellServerEdition]", "RTXPro6000BlackwellDC"),
        # A16 (GA107 die): the NVML-fallback die-label collapses to A16. The
        # slash variant (as actually stored on a fragmented install) must match
        # too, since matching is slash-insensitive.
        ("A16", "A16"),
        ("GA107GL[A2A16]", "A16"),
        ("GA107GL[A2/A16]", "A16"),
        # Unmapped, already-consistent models are identity (no-op for clean
        # installs).
        ("A40", "A40"),
        ("L40S", "L40S"),
        ("RTXA6000", "RTXA6000"),
    ],
)
def test_unify_model(stored, expected):
    assert m._unify_model(stored) == expected


def test_unify_model_passthrough_non_str():
    assert m._unify_model(None) is None
    assert m._unify_model(123) == 123


# --- _unify_then_canon: full BRAND-MODEL-SUFFIX id --------------------------
@pytest.mark.parametrize(
    "stored_id, expected",
    [
        # Blackwell: every fragmented id form -> one canonical reservable id.
        (
            "NVIDIA-GB202GL[RTXPRO6000BlackwellServerEdition]-4Q",
            "NVIDIA-RTXPro6000BlackwellDC-4Q",
        ),
        (
            "NVIDIA-RTXPRO6000BlackwellServerEdition-4Q",
            "NVIDIA-RTXPro6000BlackwellDC-4Q",
        ),
        ("NVIDIA-RTXPro6000BlackwellDC-4Q", "NVIDIA-RTXPro6000BlackwellDC-4Q"),
        # MIG dash-form suffix is canonicalised to underscore AND the model
        # unified in the same pass.
        (
            "NVIDIA-GB202GL[RTXPRO6000BlackwellServerEdition]-1-2Q",
            "NVIDIA-RTXPro6000BlackwellDC-1_2Q",
        ),
        ("NVIDIA-RTXPro6000BlackwellDC-1-3Q", "NVIDIA-RTXPro6000BlackwellDC-1_3Q"),
        # A16 die-label (incl. the slash form) -> A16.
        ("NVIDIA-GA107GL[A2/A16]-4Q", "NVIDIA-A16-4Q"),
        ("NVIDIA-A16-2Q", "NVIDIA-A16-2Q"),
        # passthrough suffix preserved.
        (
            "NVIDIA-GB202GL[RTXPRO6000BlackwellServerEdition]-passthrough",
            "NVIDIA-RTXPro6000BlackwellDC-passthrough",
        ),
        # Unmapped model: identity.
        ("NVIDIA-A40-12Q", "NVIDIA-A40-12Q"),
    ],
)
def test_unify_then_canon(stored_id, expected):
    assert m._unify_then_canon(stored_id) == expected


def test_unify_then_canon_is_idempotent():
    for sid in (
        "NVIDIA-GB202GL[RTXPRO6000BlackwellServerEdition]-1-2Q",
        "NVIDIA-GA107GL[A2/A16]-4Q",
        "NVIDIA-A40-12Q",
    ):
        once = m._unify_then_canon(sid)
        assert m._unify_then_canon(once) == once


def test_unify_then_canon_passthrough_non_vgpu():
    # Strings that are not BRAND-MODEL-SUFFIX pass through canon unchanged.
    assert m._unify_then_canon("None") == "None"
    assert m._unify_then_canon(None) is None


# --- collision-merge helpers ------------------------------------------------
def test_merge_allowed_true_wins():
    out = m._merge_allowed({"roles": ["admin"]}, {"roles": True})
    assert out["roles"] is True


def test_merge_allowed_unions_lists():
    out = m._merge_allowed(
        {"roles": ["admin"], "groups": ["g1"], "categories": False, "users": False},
        {
            "roles": ["manager"],
            "groups": ["g1", "g2"],
            "categories": False,
            "users": False,
        },
    )
    assert sorted(out["roles"]) == ["admin", "manager"]
    assert sorted(out["groups"]) == ["g1", "g2"]
    assert out["categories"] is False
    assert out["users"] is False


def test_merge_reservable_patch_maxes_capacity():
    survivor = {"allowed": {"roles": ["admin"]}, "units": 4, "heads": 1, "ram": 8192}
    loser = {"allowed": {"roles": ["admin"]}, "units": 8, "heads": 2, "ram": 4096}
    patch = m._merge_reservable_patch(survivor, loser)
    assert patch["units"] == 8
    assert patch["heads"] == 2
    assert patch["ram"] == 8192
    assert patch["allowed"]["roles"] == ["admin"]
