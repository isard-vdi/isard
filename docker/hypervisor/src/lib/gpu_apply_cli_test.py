"""Unit tests for gpu_apply_cli — the engine-invoked runtime apply CLI.

Run locally (no CI pytest gate for the hypervisor lib):
    cd docker/hypervisor/src/lib && python -m pytest gpu_apply_cli_test.py -v

The CLI contract the engine depends on: it ALWAYS prints a single parseable JSON
object to stdout (the apply report, or a {"result":"error",...} object), so the
engine can json.loads it and fall back on a non-applied result.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gpu_apply_cli as cli  # noqa: E402


def test_cli_prints_json_report(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "_build_report",
        lambda *a, **k: {"result": "applied", "applied_profile": "4Q"},
    )
    rc = cli.main(["--pci-bdf", "0000:c5:00.0", "--target-profile", "4Q"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["result"] == "applied"
    assert out["applied_profile"] == "4Q"


def test_cli_emits_json_error_on_exception(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("sysfs exploded")

    monkeypatch.setattr(cli, "_build_report", boom)
    rc = cli.main(["--pci-bdf", "0000:c5:00.0", "--target-profile", "4Q"])
    # Non-zero exit, but stdout is STILL parseable JSON so the engine can react.
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["result"] == "error"
    assert "sysfs exploded" in out["error"]


def test_cli_passes_args_through(monkeypatch, capsys):
    seen = {}

    def capture(
        pci_bdf,
        target_profile,
        action,
        mdevs_reset_at,
        mig_profile_id=None,
        mig_count=None,
        deliberate=False,
    ):
        seen.update(
            pci_bdf=pci_bdf,
            target_profile=target_profile,
            action=action,
            mdevs_reset_at=mdevs_reset_at,
            mig_profile_id=mig_profile_id,
            mig_count=mig_count,
        )
        return {"result": "noop"}

    monkeypatch.setattr(cli, "_build_report", capture)
    cli.main(
        [
            "--pci-bdf",
            "0000:c5:00.0",
            "--target-profile",
            "1g.10gb",
            "--action",
            "seed_and_apply",
            "--mdevs-reset-at",
            "2026-06-05T00:00:00",
        ]
    )
    assert seen == {
        "pci_bdf": "0000:c5:00.0",
        "target_profile": "1g.10gb",
        "action": "seed_and_apply",
        "mdevs_reset_at": "2026-06-05T00:00:00",
        "mig_profile_id": None,  # absent flag -> None -> CLI omits it downstream
        "mig_count": None,
    }


def test_cli_parses_mig_profile_id_and_count_as_int(monkeypatch):
    seen = {}

    def capture(
        pci_bdf,
        target_profile,
        action,
        mdevs_reset_at,
        mig_profile_id=None,
        mig_count=None,
        deliberate=False,
    ):
        seen["mig_profile_id"] = mig_profile_id
        seen["mig_count"] = mig_count
        return {"result": "applied"}

    monkeypatch.setattr(cli, "_build_report", capture)
    cli.main(
        [
            "--pci-bdf",
            "0000:c5:00.0",
            "--target-profile",
            "1_24Q",
            "--mig-profile-id",
            "47",
            "--mig-count",
            "4",
        ]
    )
    assert seen["mig_profile_id"] == 47
    assert seen["mig_count"] == 4


def test_build_report_seeds_mig_profile_id_when_descriptor_has_none(
    monkeypatch, tmp_path
):
    import gpu_apply
    import gpu_discovery

    monkeypatch.setattr(cli, "SETUP_GPU_LOCK", str(tmp_path / "lock"))
    monkeypatch.setattr(
        gpu_discovery,
        "build_card_descriptor",
        lambda pci_bdf, mdevs_reset_at=None: {"pci_bus_id": pci_bdf},
    )
    captured = {}
    monkeypatch.setattr(
        gpu_apply,
        "apply_target",
        lambda desc, target, deliberate=False: captured.update(desc=desc, target=target)
        or {"result": "applied"},
    )
    cli._build_report("0000:c5:00.0", "1g.24gb_me", "apply", None, mig_profile_id=19)
    assert captured["desc"]["mig_profiles"] == [
        {"name": "1g.24gb_me", "profile_id": 19}
    ]


def test_build_report_does_not_override_live_mig_profiles(monkeypatch, tmp_path):
    import gpu_apply
    import gpu_discovery

    live = [{"name": "1g.24gb_me", "profile_id": 7, "max_instances": 7}]
    monkeypatch.setattr(cli, "SETUP_GPU_LOCK", str(tmp_path / "lock"))
    monkeypatch.setattr(
        gpu_discovery,
        "build_card_descriptor",
        lambda pci_bdf, mdevs_reset_at=None: {
            "pci_bus_id": pci_bdf,
            "mig_profiles": list(live),
        },
    )
    captured = {}
    monkeypatch.setattr(
        gpu_apply,
        "apply_target",
        lambda desc, target, deliberate=False: captured.update(desc=desc)
        or {"result": "applied"},
    )
    cli._build_report("0000:c5:00.0", "1g.24gb_me", "apply", None, mig_profile_id=99)
    # The live -lgip row wins: profile_id stays 7, nothing appended.
    assert captured["desc"]["mig_profiles"] == live


def test_build_report_seeds_mig_vgpu_count_so_multi_gi_branch_runs(
    monkeypatch, tmp_path
):
    """A MIG-backed vGPU target must seed a vgpu_profiles entry carrying the
    slice count, so apply_target takes the multi-GI branch and carves N GIs --
    NOT the single-GI plain MIG path. The read-only descriptor's vgpu_profiles
    is empty when the VFs aren't live, so the count cannot be re-derived on the
    hypervisor: the engine passes it via --mig-count."""
    import gpu_apply
    import gpu_discovery

    monkeypatch.setattr(cli, "SETUP_GPU_LOCK", str(tmp_path / "lock"))
    monkeypatch.setattr(
        gpu_discovery,
        "build_card_descriptor",
        lambda pci_bdf, mdevs_reset_at=None: {
            "pci_bus_id": pci_bdf
        },  # no vgpu_profiles
    )
    captured = {}
    monkeypatch.setattr(
        gpu_apply,
        "apply_target",
        lambda desc, target, deliberate=False: captured.update(desc=desc)
        or {"result": "applied"},
    )
    cli._build_report(
        "0000:05:00.0", "1_24Q", "apply", None, mig_profile_id=47, mig_count=4
    )
    entry = gpu_apply._mig_vgpu_entry(captured["desc"], "1_24Q")
    assert entry is not None
    assert entry["mig_profile_id"] == 47
    assert entry["mig_count"] == 4
