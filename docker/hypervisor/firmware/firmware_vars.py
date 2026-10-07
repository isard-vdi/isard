#!/usr/bin/env python3
"""Verify the isard OVMF Secure Boot varstore (verify) and describe it (manifest)."""

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys

REQUIRED_CERTS = {
    "PK": {"Red Hat Secure Boot (PK/KEK key 1)"},
    "KEK": {
        "Red Hat Secure Boot (PK/KEK key 1)",
        "Microsoft Corporation KEK CA 2011",
        "Microsoft Corporation KEK 2K CA 2023",
    },
    "db": {
        "Microsoft Windows Production PCA 2011",
        "Microsoft Corporation UEFI CA 2011",
        "Windows UEFI CA 2023",
        "Microsoft UEFI CA 2023",
        "Microsoft Option ROM UEFI CA 2023",
    },
}
# The vendored DBXUpdate.bin carries exactly this many sha256 revocations.
EXPECTED_DBX_SHA256_COUNT = 443


def run_print(vars_path):
    out = subprocess.run(
        ["virt-fw-vars", "--input", vars_path, "--print", "--verbose"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


def parse_print_output(text):
    variables = {}
    current_var = None
    current_type = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("name="):
            current_var = stripped.split()[0][len("name=") :]
            current_type = None
            variables.setdefault(current_var, {"x509": [], "sha256_count": 0})
        elif stripped.startswith("siglist type=") and current_var is not None:
            current_type = stripped.split("type=", 1)[1].split()[0]
            if "EfiCertSha256" in current_type and "count=" in stripped:
                variables[current_var]["sha256_count"] += int(
                    stripped.split("count=", 1)[1].split()[0]
                )
        elif stripped.startswith("subject CN=") and current_var is not None:
            if current_type and "EfiCertX509" in current_type:
                variables[current_var]["x509"].append(stripped[len("subject CN=") :])
    return variables


def check(variables):
    errors = []
    for var, required in REQUIRED_CERTS.items():
        found = set(variables.get(var, {}).get("x509", []))
        for missing in sorted(required - found):
            errors.append(f"{var}: required certificate missing: {missing}")
    dbx = variables.get("dbx", {"x509": [], "sha256_count": 0})
    for cn in sorted(REQUIRED_CERTS["db"] & set(dbx["x509"])):
        errors.append(f"dbx: db certificate revoked in dbx: {cn}")
    if dbx["sha256_count"] != EXPECTED_DBX_SHA256_COUNT:
        errors.append(
            f"dbx: expected {EXPECTED_DBX_SHA256_COUNT} sha256 revocations, "
            f"found {dbx['sha256_count']}"
        )
    return errors


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cmd_verify(args):
    variables = parse_print_output(run_print(args.vars))
    for var in ("PK", "KEK", "db"):
        print(f"{var}: {sorted(variables.get(var, {}).get('x509', []))}")
    print(f"dbx sha256 revocations: {variables.get('dbx', {}).get('sha256_count', 0)}")
    errors = check(variables)
    if errors:
        print("FAIL: isard OVMF varstore rejected:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("OK: isard OVMF varstore has every required certificate and a clean dbx.")
    return 0


def cmd_manifest(args):
    variables = parse_print_output(run_print(args.vars))
    if check(variables):
        print(
            "refusing to write manifest for a varstore that fails verify",
            file=sys.stderr,
        )
        return 1
    manifest = {
        "version": args.version,
        "source": {
            "vars": "OVMF_VARS_4M.fd",
            "ovmf": args.ovmf,
            "tool": f"virt-firmware {importlib.metadata.version('virt-firmware')}",
        },
        "file": "OVMF_VARS_4M.isard-ms.fd",
        "sha256": _sha256(args.vars),
        "dbx": {
            "source": "DBXUpdate.bin",
            "sha256": _sha256(args.dbx),
            "sha256_count": variables["dbx"]["sha256_count"],
        },
        "certificates": {
            var: sorted(variables.get(var, {}).get("x509", []))
            for var in ("PK", "KEK", "db")
        },
    }
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify")
    v.add_argument("--vars", required=True)
    v.set_defaults(func=cmd_verify)

    m = sub.add_parser("manifest")
    m.add_argument("--vars", required=True)
    m.add_argument("--dbx", required=True)
    m.add_argument("--version", required=True)
    m.add_argument("--ovmf", required=True)
    m.add_argument("--out", required=True)
    m.set_defaults(func=cmd_manifest)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
