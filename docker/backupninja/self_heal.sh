#!/bin/sh

# Hourly self-heal: if /usr/local/etc/backup.d/ is empty (or has no
# enabled job files), re-run the setup phase of run.sh. This catches
# the case where the boot-time NFS mount in run.sh failed and the
# directory was never populated; without this, a single transient
# unreachability at container start leaves the container in a
# permanently broken backup state until someone restarts it.
#
# Threshold of 5 entries is generous: even a minimal config (one
# backup type + session start/end + nfs mount/umount markers) produces
# more than 5 files. An empty or 1-2-entry directory means setup
# never finished.

count=$(ls /usr/local/etc/backup.d/ 2>/dev/null | wc -l)
if [ "$count" -lt 5 ]; then
    LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"
    timestamp=$(date '+%b %d %H:%M:%S')
    echo "$timestamp Warning: backupninja-self-heal: backup.d has only $count entries; re-running setup" >> "$LOG_FILE"

    # Skip if another setup is in flight; run.sh's internal flock would
    # also refuse, but probing here keeps the log noise readable.
    if ! ( flock -n 9 || exit 1 ) 9>/var/lock/backupninja-setup.lock; then
        echo "$timestamp Info: self-heal: another setup is running; skipping" >> "$LOG_FILE"
        exit 0
    fi

    /usr/local/bin/run.sh setup >> "$LOG_FILE" 2>&1 || true
    new_count=$(ls /usr/local/etc/backup.d/ 2>/dev/null | wc -l)
    timestamp=$(date '+%b %d %H:%M:%S')
    echo "$timestamp Info: backupninja-self-heal: setup finished, backup.d now has $new_count entries" >> "$LOG_FILE"
fi
