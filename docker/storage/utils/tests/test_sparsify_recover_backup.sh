#!/bin/bash
#===============================================================================
# Suite: sparsify recovery trap (_sparsify_recover_backup)
#===============================================================================
# Drives the trap handler against real qcow2 images in every state it can meet
# when the script is killed mid-sparsify: clean, still locked by a live holder,
# corrupt beyond opening, corrupt but openable, and destination gone.
#
# Requires qemu-img and qemu-io (Alpine: apk add qemu-img).
# Run it with: make test-sparsify
#===============================================================================

set -u -o pipefail

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SPARSIFY="$TESTS_DIR/../sparsify"

for cmd in qemu-img qemu-io; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "FATAL: $cmd is required by this suite (apk add qemu-img)" >&2
        exit 2
    fi
done

# Sourcing must define the helpers without running the tool
# shellcheck source=../sparsify
source "$SPARSIFY"

if ! declare -F _sparsify_recover_backup >/dev/null; then
    echo "FATAL: sourcing $SPARSIFY did not define _sparsify_recover_backup" >&2
    exit 2
fi

WORK_DIR=$(mktemp -d)
HOLDER_PID=""
FAILURES=0
TESTS=0

cleanup_suite() {
    [ -n "$HOLDER_PID" ] && kill -9 "$HOLDER_PID" 2>/dev/null
    rm -rf "$WORK_DIR"
}
trap cleanup_suite EXIT

pass() { TESTS=$((TESTS + 1)); echo "ok $TESTS - $1"; }
fail() {
    TESTS=$((TESTS + 1))
    FAILURES=$((FAILURES + 1))
    echo "not ok $TESTS - $1"
    [ $# -gt 1 ] && echo "  # $2"
    return 0
}

check() {
    local name="$1" condition="$2" detail="${3:-}"
    if eval "$condition"; then
        pass "$name"
    else
        fail "$name" "failed: $condition${detail:+ | $detail}"
    fi
}

sum_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# $1 destination path, $2 fill pattern; a distinct pattern per file makes the
# branch the handler took visible in the checksums
make_image() {
    qemu-img create -f qcow2 "$1" 64M >/dev/null 2>&1
    qemu-io -c "write -P $2 0 1M" -f qcow2 "$1" >/dev/null 2>&1
}

# Wreck the L1 table: the image still opens, qemu-img check reports corruption
# (measured: exit 2).
corrupt_l1() {
    dd if=/dev/urandom of="$1" bs=1 seek=196608 count=4096 conv=notrunc status=none
}

# Scribble the header fields (cluster_bits etc.) but keep the qcow2 magic: the
# image can no longer be opened (measured: exit 1, "Could not open ...
# Unsupported cluster size"), with no lock message -> classified dirty.
corrupt_header() {
    dd if=/dev/urandom of="$1" bs=1 seek=8 count=32 conv=notrunc status=none
}

# Read an 8-byte big-endian integer at $2 from file $1 (bash 64-bit arithmetic
# copes with the top COPIED bit being set). Uses only dd + od, present in the
# Alpine CI image; no python.
read_be64() {
    local hex
    hex=$(dd if="$1" bs=1 skip="$2" count=8 status=none 2>/dev/null | od -An -tx1 | tr -d ' \n')
    printf '%d' "$((16#$hex))"
}

# Build a qcow2 with a genuine leaked cluster: allocate one data cluster, then
# zero its L2 entry so the cluster stays refcounted but unreferenced. qemu-img
# check then reports "Leaked cluster ... no harm to data" (measured: exit 3).
make_leaked() {
    make_image "$1" 0x55
    local l1_off l1e l2_off
    l1_off=$(read_be64 "$1" 40)             # header.l1_table_offset @ byte 40
    l1e=$(read_be64 "$1" "$l1_off")         # first L1 entry
    l2_off=$(( l1e & 0x00fffffffffffe00 ))  # mask flags -> L2 table offset
    dd if=/dev/zero of="$1" bs=1 seek="$l2_off" count=8 conv=notrunc status=none
}

# Wipe the qcow2 magic: the file is probed as raw, which does not support
# checks. For a file that was a qcow2 this means its identity is destroyed
# (measured: exit 63, "This image format does not support checks").
wipe_magic() {
    make_image "$1" 0x11
    dd if=/dev/zero of="$1" bs=1 seek=0 count=4 conv=notrunc status=none
}

start_holder() {
    local file="$1"
    local fifo="$WORK_DIR/holder.fifo"
    local log="$WORK_DIR/holder.log"
    rm -f "$fifo"
    mkfifo "$fifo"
    : > "$log"
    qemu-io -f qcow2 "$file" <"$fifo" >"$log" 2>&1 &
    HOLDER_PID=$!
    exec 9>"$fifo"
    # Readiness WITHOUT competing for the lock. qemu-io prints its "qemu-io>"
    # prompt only after it has opened the image and taken the write lock, so the
    # prompt landing in the log proves the lock is held. The old readiness probe
    # was `qemu-img check`, which opens the image and takes its own (shared)
    # lock; measured on qemu-img 9.2.4/10.0.0 that probe makes the holder's
    # exclusive-write-lock acquisition fail ~32% of the time under load
    # ("Failed to get write lock"), i.e. the suite raced and killed the very
    # holder it was waiting for. Watching the prompt takes no lock at all.
    # generous: qemu-io startup can be slow on a loaded runner, and a holder that
    # never takes the lock would silently turn the locked case into a false pass
    local waited=0
    while [ "$waited" -lt 300 ]; do
        kill -0 "$HOLDER_PID" 2>/dev/null || break
        grep -q "qemu-io>" "$log" 2>/dev/null && return 0
        sleep 0.1
        waited=$((waited + 1))
    done
    echo "FATAL: holder never took the qcow2 lock on $file" >&2
    echo "  holder pid=$HOLDER_PID alive=$(kill -0 "$HOLDER_PID" 2>/dev/null && echo yes || echo no)" >&2
    echo "  holder log: [$(cat "$log" 2>/dev/null)]" >&2
    exit 2
}

stop_holder() {
    exec 9>&-
    [ -n "$HOLDER_PID" ] && wait "$HOLDER_PID" 2>/dev/null
    HOLDER_PID=""
}

echo "# $(qemu-img --version | head -1)"

#-------------------------------------------------------------------------------
echo "# case 1: destination is clean -> drop the backup"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/clean.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
make_image "$backup" 0x22
dest_sum=$(sum_of "$dest")

_sparsify_recover_backup "$dest" "$backup"

check "clean: backup removed" '[ ! -e "$backup" ]'
check "clean: destination untouched" '[ "$(sum_of "$dest")" = "$dest_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 2: destination still locked by a live holder -> keep the backup"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/locked.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
make_image "$backup" 0x22
dest_sum=$(sum_of "$dest")
backup_sum=$(sum_of "$backup")
start_holder "$dest"

SPARSIFY_RECOVER_SETTLE_TIMEOUT=2 _sparsify_recover_backup "$dest" "$backup"

check "locked: backup kept" '[ -f "$backup" ]'
check "locked: backup contents intact" '[ "$(sum_of "$backup")" = "$backup_sum" ]'
check "locked: destination not overwritten" '[ "$(sum_of "$dest")" = "$dest_sum" ]'
stop_holder

#-------------------------------------------------------------------------------
echo "# case 3: holder dies during the settle wait -> decide once it is gone"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/settles.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
make_image "$backup" 0x22
dest_sum=$(sum_of "$dest")
start_holder "$dest"
(sleep 2; echo quit >"$WORK_DIR/holder.fifo") &
releaser=$!

SPARSIFY_RECOVER_SETTLE_TIMEOUT=20 _sparsify_recover_backup "$dest" "$backup"

wait "$releaser" 2>/dev/null
stop_holder
check "settled: backup removed once the lock cleared" '[ ! -e "$backup" ]'
check "settled: destination untouched" '[ "$(sum_of "$dest")" = "$dest_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 4: destination corrupt but openable -> restore the backup"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/corrupt.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
corrupt_l1 "$dest"
make_image "$backup" 0x22
backup_sum=$(sum_of "$backup")

_sparsify_recover_backup "$dest" "$backup"

check "corrupt: backup consumed" '[ ! -e "$backup" ]'
check "corrupt: destination replaced by the backup" '[ "$(sum_of "$dest")" = "$backup_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 5: header fields wrecked (magic kept), image cannot be opened, rc 1 -> restore"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/badheader.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
corrupt_header "$dest"
make_image "$backup" 0x22
backup_sum=$(sum_of "$backup")

_sparsify_recover_backup "$dest" "$backup"

check "bad header: backup consumed" '[ ! -e "$backup" ]'
check "bad header: destination replaced by the backup" '[ "$(sum_of "$dest")" = "$backup_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 6: destination gone -> restore"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/missing.qcow2"
backup="${dest}.sparsify-backup"
make_image "$backup" 0x22
backup_sum=$(sum_of "$backup")

_sparsify_recover_backup "$dest" "$backup"

check "missing: backup consumed" '[ ! -e "$backup" ]'
check "missing: destination restored from the backup" '[ "$(sum_of "$dest")" = "$backup_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 7: handler reachable from the xargs worker shells"
#-------------------------------------------------------------------------------
dest="$WORK_DIR/worker.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11
make_image "$backup" 0x22
dest_sum=$(sum_of "$dest")
export_worker_context

bash -c '_sparsify_recover_backup "$1" "$2"' _ "$dest" "$backup"

check "worker shell: backup removed" '[ ! -e "$backup" ]'
check "worker shell: destination untouched" '[ "$(sum_of "$dest")" = "$dest_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 8: destination has only leaked clusters (rc 3, no harm to data) -> drop the backup"
#-------------------------------------------------------------------------------
# The likeliest aftermath of killing a qcow2 writer. The destination is fully
# usable, so the trap must NOT keep it in limbo asking for manual recovery.
dest="$WORK_DIR/leaked.qcow2"
backup="${dest}.sparsify-backup"
make_leaked "$dest"
make_image "$backup" 0x22
dest_sum=$(sum_of "$dest")
check "leaked: precondition qemu-img check reports rc 3" \
    'out=$(qemu-img check -q "$dest" 2>&1); [ $? -eq 3 ]'
check "leaked: classified clean" '[ "$(_sparsify_image_state "$dest")" = clean ]'

_sparsify_recover_backup "$dest" "$backup"

check "leaked: backup dropped (dest usable)" '[ ! -e "$backup" ]'
check "leaked: destination untouched" '[ "$(sum_of "$dest")" = "$dest_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 9: destination magic wiped (rc 63, not a qcow2 anymore) -> restore the backup"
#-------------------------------------------------------------------------------
# A file that was a qcow2 no longer identifies as one: its identity is
# destroyed. Keeping it live while the good backup sits beside it is the exact
# dangerous-direction bug; it must restore.
dest="$WORK_DIR/wiped.qcow2"
backup="${dest}.sparsify-backup"
wipe_magic "$dest"
make_image "$backup" 0x22
backup_sum=$(sum_of "$backup")
check "wiped: precondition qemu-img check reports rc 63" \
    'out=$(qemu-img check -q "$dest" 2>&1); [ $? -eq 63 ]'
check "wiped: classified dirty" '[ "$(_sparsify_image_state "$dest")" = dirty ]'

_sparsify_recover_backup "$dest" "$backup"

check "wiped: backup consumed" '[ ! -e "$backup" ]'
check "wiped: destination restored from the backup" '[ "$(sum_of "$dest")" = "$backup_sum" ]'

#-------------------------------------------------------------------------------
echo "# case 10: EXIT trap fires the exported handler in a killed xargs -P worker (not command-not-found)"
#-------------------------------------------------------------------------------
# The real parallel path is `xargs -P bash -c 'process_file ...'`; the recovery
# trap is armed inside those worker shells. This reproduces it: a worker arms
# the same EXIT trap, then dies mid-run by a signal with the trap still armed.
# Before the handler was added to the exported context this printed
# "_sparsify_recover_backup: command not found" and orphaned the backup.
dest="$WORK_DIR/trapworker.qcow2"
backup="${dest}.sparsify-backup"
make_image "$dest" 0x11        # clean dest -> a working handler drops the backup
make_image "$backup" 0x22
export_worker_context
errlog="$WORK_DIR/trapworker.err"
printf '%s\n' "$dest" | xargs -I{} -P2 bash -c '
    trap "_sparsify_recover_backup \"$1\" \"$2\"" EXIT INT TERM
    kill -HUP $$
    sleep 5
' _ {} "$backup" 2>"$errlog"

check "xargs worker: handler executed, no command-not-found" \
    '! grep -q "command not found" "$errlog"'
check "xargs worker: whole exported chain ran -> clean dest dropped the backup" \
    '[ ! -e "$backup" ]'

#-------------------------------------------------------------------------------
echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "# FAILED $FAILURES of $TESTS"
    exit 1
fi
echo "# passed $TESTS"
