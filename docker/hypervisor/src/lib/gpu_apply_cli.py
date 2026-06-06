#!/usr/bin/env python3
"""CLI so the engine can invoke the hypervisor's LOCAL GPU apply over SSH for a
runtime profile change, instead of building + SSHing the host-command sequences
itself (which duplicated the apply orchestration). One source of truth for the
apply mechanism: ``gpu_apply.apply_target``.

Usage:
    python3 /src/lib/gpu_apply_cli.py --pci-bdf <BDF> --target-profile <suffix> \
        [--action apply|seed_and_apply] [--mdevs-reset-at <iso-ts>] \
        [--mig-profile-id <int>]

Behaviour:
  * Builds the card's descriptor READ-ONLY (``gpu_discovery.build_card_descriptor``
    -- no discovery reset / SR-IOV cycle, so other cards' pools and live desktops
    are untouched).
  * For a MIG target the engine passes ``--mig-profile-id`` (the durable
    GPU-instance profile id from ``vgpus.info.types[<profile>]["mig_profile_id"]``):
    a MIG-DISABLED card lists nothing in ``nvidia-smi mig -lgip``, so the read-only
    descriptor carries no ``mig_profiles`` and ``apply_target`` would treat the MIG
    target as a plain vGPU carve. We seed it into the descriptor ONLY for the target
    suffix and ONLY when the live probe didn't already surface it.
  * Takes the shared ``/run/isard-hyp-setup.lock`` (the SAME lock the registration
    apply and the engine's ``flock(1)`` batches use) so a runtime apply cannot
    race them.
  * Applies via ``gpu_apply.apply_target`` and prints ONLY the JSON report to
    stdout; all logging goes to stderr.
  * On ANY error it still prints a JSON error object to stdout (and exits
    non-zero) so the engine always gets parseable output and can fall back.
"""

import argparse
import fcntl
import json
import os
import sys

SETUP_GPU_LOCK = "/run/isard-hyp-setup.lock"


def _build_report(pci_bdf, target_profile, action, mdevs_reset_at, mig_profile_id=None):
    # Imports are deferred so an argparse/usage error doesn't depend on the
    # GPU libs being importable. gpu_apply + gpu_discovery live beside this file.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gpu_apply
    import gpu_discovery

    desc = gpu_discovery.build_card_descriptor(pci_bdf, mdevs_reset_at=mdevs_reset_at)

    # Seed the durable MIG profile id when the live -lgip probe found none for
    # the target (MIG-disabled card). Live rows always win: only fill the gap
    # for this target suffix so a card already in MIG mode keeps its real data.
    if mig_profile_id is not None:
        existing = desc.get("mig_profiles") or []
        have = {gpu_apply.canonical_suffix(m.get("name")) for m in existing}
        if gpu_apply.canonical_suffix(target_profile) not in have:
            desc["mig_profiles"] = existing + [
                {"name": target_profile, "profile_id": mig_profile_id}
            ]

    target = {"target_profile": target_profile, "action": action}

    lock_fd = os.open(SETUP_GPU_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        return gpu_apply.apply_target(desc, target)
    finally:
        # Guard the release so a flock/close error can never mask the real
        # exception from apply_target (closing the fd releases the lock anyway).
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply one GPU card's profile locally")
    parser.add_argument("--pci-bdf", required=True)
    parser.add_argument("--target-profile", required=True)
    parser.add_argument("--action", default="apply")
    parser.add_argument("--mdevs-reset-at", default=None)
    parser.add_argument("--mig-profile-id", default=None, type=int)
    args = parser.parse_args(argv)

    try:
        report = _build_report(
            args.pci_bdf,
            args.target_profile,
            args.action,
            args.mdevs_reset_at,
            args.mig_profile_id,
        )
        print(json.dumps(report))
        return 0
    except Exception as e:  # noqa: BLE001 -- always emit parseable output
        print(json.dumps({"result": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
