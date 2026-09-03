#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Unit test for build.sh's _require_qcow2_only_on_apiv4 guard: a flavour that
# does not run apiv4 must NOT declare QCOW2_* keys, since apiv4 is the only
# reader now and they would be inert (silent geometry loss). Extracts the real
# function from build.sh (no copy that could drift) and exercises it.
set -u

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD_SH="$REPO_ROOT/build.sh"

# Pull the function body out of build.sh and define it in this shell.
_fn="$(sed -n '/^_require_qcow2_only_on_apiv4()/,/^}/p' "$BUILD_SH")"
if [ -z "$_fn" ]; then
	echo "FAIL: _require_qcow2_only_on_apiv4 not found in build.sh"
	exit 1
fi
eval "$_fn"

fails=0
_reset_qcow2() {
	unset QCOW2_CLUSTER_SIZE QCOW2_EXTENDED_L2 QCOW2_LAZY_REFCOUNTS QCOW2_PREALLOCATION
}

# 1. non-apiv4 flavour with a QCOW2_* key set -> must fail (exit != 0).
_reset_qcow2
parts="db storage engine"
QCOW2_CLUSTER_SIZE="128k"
if _require_qcow2_only_on_apiv4 "storage" >/dev/null 2>&1; then
	echo "FAIL: storage flavour with QCOW2_CLUSTER_SIZE set did not error"
	fails=$((fails + 1))
else
	echo "ok: storage flavour with QCOW2_* set errors"
fi

# 2. non-apiv4 flavour, another QCOW2_* key -> must fail.
_reset_qcow2
parts="db storage"
QCOW2_PREALLOCATION="metadata"
if _require_qcow2_only_on_apiv4 "hypervisor" >/dev/null 2>&1; then
	echo "FAIL: hypervisor flavour with QCOW2_PREALLOCATION set did not error"
	fails=$((fails + 1))
else
	echo "ok: hypervisor flavour with QCOW2_PREALLOCATION set errors"
fi

# 3. apiv4-bearing flavour with QCOW2_* set -> OK (apiv4 reads them).
_reset_qcow2
parts="db apiv4 engine storage"
QCOW2_CLUSTER_SIZE="128k"
if _require_qcow2_only_on_apiv4 "all-in-one" >/dev/null 2>&1; then
	echo "ok: all-in-one flavour with QCOW2_* set is allowed"
else
	echo "FAIL: all-in-one flavour with QCOW2_* set was rejected"
	fails=$((fails + 1))
fi

# 4. non-apiv4 flavour with NO QCOW2_* keys -> OK.
_reset_qcow2
parts="db storage engine"
if _require_qcow2_only_on_apiv4 "storage" >/dev/null 2>&1; then
	echo "ok: storage flavour with no QCOW2_* is allowed"
else
	echo "FAIL: storage flavour with no QCOW2_* was rejected"
	fails=$((fails + 1))
fi

if [ "$fails" -ne 0 ]; then
	echo "FAILED: $fails case(s)"
	exit 1
fi
echo "PASS"
