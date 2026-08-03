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
corrupt_l1() {
    dd if=/dev/urandom of="$1" bs=1 seek=196608 count=4096 conv=notrunc status=none
}

# Wreck the header: the image cannot be opened at all
corrupt_header() {
    dd if=/dev/urandom of="$1" bs=1 seek=8 count=32 conv=notrunc status=none
}

start_holder() {
    local file="$1"
    local fifo="$WORK_DIR/holder.fifo"
    rm -f "$fifo"
    mkfifo "$fifo"
    qemu-io -f qcow2 "$file" <"$fifo" >"$WORK_DIR/holder.log" 2>&1 &
    HOLDER_PID=$!
    exec 9>"$fifo"
    # generous: qemu-io startup can be slow on a loaded runner, and a holder that
    # never takes the lock would silently turn case 2 into a false pass
    local waited=0 probe=""
    while [ "$waited" -lt 300 ]; do
        kill -0 "$HOLDER_PID" 2>/dev/null || break
        # not a pipe into grep: pipefail would report qemu-img's status, not the match
        probe=$(qemu-img check -q "$file" 2>&1)
        case "$probe" in
            *"Failed to get"*) return 0 ;;
        esac
        sleep 0.1
        waited=$((waited + 1))
    done
    echo "FATAL: holder never took the qcow2 lock on $file" >&2
    echo "  holder pid=$HOLDER_PID alive=$(kill -0 "$HOLDER_PID" 2>/dev/null && echo yes || echo no)" >&2
    echo "  holder log: [$(cat "$WORK_DIR/holder.log" 2>/dev/null)]" >&2
    echo "  last probe: [$probe]" >&2
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
echo "# case 5: destination header wrecked, cannot be opened -> restore"
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
echo "1..$TESTS"
if [ "$FAILURES" -gt 0 ]; then
    echo "# FAILED $FAILURES of $TESTS"
    exit 1
fi
echo "# passed $TESTS"
