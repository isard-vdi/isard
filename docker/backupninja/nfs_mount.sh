#!/bin/sh

# Mount the configured NFS share at /backup, with retry/backoff so a
# transient unreachability at container start (NFS server still booting,
# brief network blip, coordinated stack restart, etc.) does not leave the
# container with no backup configuration.
#
# Tunable via environment:
#   BACKUP_NFS_MOUNT_RETRIES         (default 10)
#   BACKUP_NFS_MOUNT_BACKOFF_SECONDS (default 30)
#
# Default budget: 10 attempts × 30s = 5 minutes before giving up.
# Exits 0 on success (or if already mounted), exits 1 after exhausting retries.

retries="${BACKUP_NFS_MOUNT_RETRIES:-10}"
backoff="${BACKUP_NFS_MOUNT_BACKOFF_SECONDS:-30}"
target="$BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"

if [ -z "$BACKUP_NFS_SERVER" ] || [ -z "$BACKUP_NFS_FOLDER" ]; then
    echo "ERROR!!! BACKUP_NFS_SERVER or BACKUP_NFS_FOLDER not set !!!"
    exit 1
fi

# Already mounted? Nothing to do.
if grep -qs "$target" /proc/mounts; then
    echo "BACKUP NFS FOLDER already mounted: $target"
    exit 0
fi

mkdir -p /backup

i=0
while [ "$i" -lt "$retries" ]; do
    i=$((i + 1))
    if mount -t nfs4 -o soft,timeo=600,retrans=3 "$target" /backup 2>/tmp/nfs_mount.err; then
        if grep -qs "$target" /proc/mounts; then
            echo "BACKUP NFS FOLDER MOUNTED: $target (attempt $i/$retries)"
            exit 0
        fi
    fi
    if [ "$i" -lt "$retries" ]; then
        echo "Mount attempt $i/$retries failed for $target; retrying in ${backoff}s"
        [ -s /tmp/nfs_mount.err ] && sed 's/^/  /' /tmp/nfs_mount.err
        sleep "$backoff"
    fi
done

echo "ERROR!!! UNABLE TO MOUNT $target after $retries attempts !!!"
[ -s /tmp/nfs_mount.err ] && sed 's/^/  /' /tmp/nfs_mount.err
exit 1
