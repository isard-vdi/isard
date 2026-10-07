#!/usr/bin/env bash
# ovmf build stage: enroll the isard Secure Boot varstore, verify it, write its manifest.
set -euo pipefail

ISARD_DIR=/usr/share/OVMF/isard
SRC_VARS=/usr/share/OVMF/OVMF_VARS_4M.fd
DBX=/firmware-src/DBXUpdate.bin
OUT="$ISARD_DIR/OVMF_VARS_4M.isard-ms.fd"

mkdir -p "$ISARD_DIR"

virt-fw-vars \
  --input "$SRC_VARS" \
  --output "$OUT" \
  --enroll-redhat \
  --microsoft-kek all \
  --microsoft-db all \
  --set-dbx "$DBX" \
  --secure-boot

python3 /firmware-src/firmware_vars.py verify --vars "$OUT"

python3 /firmware-src/firmware_vars.py manifest \
  --vars "$OUT" \
  --dbx "$DBX" \
  --version 2026.09-1 \
  --ovmf "$(dpkg-query -W -f='${Version}' ovmf)" \
  --out "$ISARD_DIR/firmware-vars.json"

echo "== isard OVMF vars =="
sha256sum "$OUT"
cat "$ISARD_DIR/firmware-vars.json"
