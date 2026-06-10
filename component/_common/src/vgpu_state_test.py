"""Unit tests for the shared applied-state patch builder."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import vgpu_state as vs  # noqa: E402


def test_seeds_requested_when_unset():
    patch = vs.build_applied_state_patch(
        {"requested_profile": None},
        "4Q",
        {"4Q": {"u1": {"created": True}}},
        "2026-06-05T00:00:00",
    )
    assert patch["vgpu_profile"] == "4Q"
    assert patch["requested_profile"] == "4Q"  # seeded
    assert patch["mdevs"] == {"4Q": {"u1": {"created": True}}}
    assert patch["mdevs_last_synced_at"] == "2026-06-05T00:00:00"  # no-fight key
    assert patch["changing_to_profile"] is False
    assert "operator_passthrough" not in patch  # only for passthrough seed


def test_does_not_clobber_existing_requested_profile():
    patch = vs.build_applied_state_patch(
        {"requested_profile": "8Q", "operator_passthrough": False},
        "4Q",
        {"4Q": {}},
        "ts",
    )
    assert "requested_profile" not in patch  # preserved existing operator intent
    assert "operator_passthrough" not in patch


def test_passthrough_first_time_sets_operator_flag():
    patch = vs.build_applied_state_patch({}, "passthrough", {"passthrough": {}}, "ts")
    assert patch["requested_profile"] == "passthrough"
    assert patch["operator_passthrough"] is True


def test_mdevs_replace_not_merge():
    # host is authoritative -> patch carries exactly the reported pool
    patch = vs.build_applied_state_patch(
        {"requested_profile": "4Q", "mdevs": {"2Q": {"old": {}}}},
        "4Q",
        {"4Q": {"new": {}}},
        "ts",
    )
    assert patch["mdevs"] == {"4Q": {"new": {}}}


def test_mig_pool_persisted_verbatim():
    # A MIG runtime change (now also routed via gpu_apply_cli) reports a pool
    # entry carrying mig=True + mig_profile_id; ingest must persist it verbatim
    # and set the MIG suffix as the current profile.
    mig_pool = {
        "1g.24gb_me": {
            "uuid-1": {
                "pci_mdev_id": "0000:c5:00.0",
                "type_id": "1g.24gb_me",
                "created": True,
                "mig": True,
                "mig_profile_id": 19,
            }
        }
    }
    patch = vs.build_applied_state_patch(
        {"requested_profile": "1g.24gb_me"}, "1g.24gb_me", mig_pool, "ts"
    )
    assert patch["vgpu_profile"] == "1g.24gb_me"
    assert patch["mdevs"] == mig_pool


def test_missing_reset_at_omits_sync_key():
    patch = vs.build_applied_state_patch({"requested_profile": "4Q"}, "4Q", {}, None)
    assert "mdevs_last_synced_at" not in patch


def test_sets_applied_by_hypervisor_flag():
    patch = vs.build_applied_state_patch({"requested_profile": "4Q"}, "4Q", {}, "ts")
    assert patch["applied_by_hypervisor"] is True


# --- parse_apply_report (engine falls back to inline apply on None) ---
def test_parse_apply_report_valid_applied():
    report = vs.parse_apply_report(
        '{"result": "applied", "applied_profile": "4Q", "mdevs": {"4Q": {}}}'
    )
    assert report["result"] == "applied"
    assert report["applied_profile"] == "4Q"


def test_parse_apply_report_valid_error():
    report = vs.parse_apply_report('{"result": "error", "error": "boom"}')
    assert report["result"] == "error" and report["error"] == "boom"


def test_parse_apply_report_blank_returns_none():
    assert vs.parse_apply_report("") is None
    assert vs.parse_apply_report(None) is None


def test_parse_apply_report_garbage_returns_none():
    # non-JSON stdout (e.g. a python traceback leaked to stdout) -> fall back
    assert vs.parse_apply_report("Traceback (most recent call last):") is None


def test_parse_apply_report_non_report_json_returns_none():
    # valid JSON but not a report object (no result / not a dict) -> fall back
    assert vs.parse_apply_report('{"foo": 1}') is None
    assert vs.parse_apply_report("[1, 2, 3]") is None
    assert vs.parse_apply_report('"applied"') is None


# --- reconcile_pool_to_live --------------------------------------------------
def test_reconcile_replaces_stale_uuids_with_host_set():
    db = {
        "8Q": {
            "old": {"created": True, "domain_started": False, "domain_reserved": False}
        }
    }
    live = {
        "8Q": {
            "new": {
                "pci_mdev_id": "0000:d4:00.2",
                "type_id": "nvidia-1525",
                "created": True,
                "domain_started": False,
                "domain_reserved": False,
            }
        }
    }
    out = vs.reconcile_pool_to_live(db, live)
    assert set(out["8Q"]) == {"new"}  # stale 'old' dropped, host 'new' added free
    assert out["8Q"]["new"]["domain_started"] is False


def test_reconcile_adopts_running_desktop():
    db = {
        "8Q": {
            "u": {
                "created": True,
                "domain_started": "desk1",
                "domain_reserved": "desk1",
            }
        }
    }
    live = {
        "8Q": {
            "u": {
                "pci_mdev_id": "0000:d4:00.3",
                "type_id": "nvidia-1525",
                "created": True,
                "domain_started": False,
                "domain_reserved": False,
            }
        }
    }
    out = vs.reconcile_pool_to_live(db, live)
    assert out["8Q"]["u"]["domain_started"] == "desk1"  # never drop a running desktop
    assert out["8Q"]["u"]["domain_reserved"] == "desk1"


def test_reconcile_drops_sibling_profile_pools():
    # A card carved to 8Q: a stale sibling 4Q pool in the DB is dropped (reality).
    db = {"4Q": {"x": {"created": True}}, "8Q": {"y": {"created": True}}}
    live = {
        "8Q": {
            "z": {
                "pci_mdev_id": "p",
                "type_id": "t",
                "created": True,
                "domain_started": False,
                "domain_reserved": False,
            }
        }
    }
    out = vs.reconcile_pool_to_live(db, live)
    assert set(out) == {"8Q"} and set(out["8Q"]) == {"z"}
