#!/bin/sh
# backupninja's sh handler ignores exit codes and only counts Warning:/Error: lines
repo="$1"

[ -d "$repo" ] || exit 0

echo "Compacting Borg repository at $repo..."
out=$(borg compact --cleanup-commits --verbose --threshold 5 "$repo" 2>&1)
rc=$?
[ -n "$out" ] && printf '%s\n' "$out"

[ "$rc" -eq 0 ] && exit 0

if printf '%s\n' "$out" | grep -q "Failed to create/acquire the lock"; then
    echo "Warning: borg compact skipped for $repo: the repository is locked by another borg process"
elif [ "$rc" -eq 1 ]; then
    echo "Warning: borg compact finished with warnings for $repo (exit $rc)"
else
    echo "Error: borg compact failed for $repo (exit $rc)"
fi
exit "$rc"
