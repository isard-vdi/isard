#!/bin/sh

# a borg from another session or a manual run may still be writing to /backup
if pgrep -x borg >/dev/null 2>&1; then
    echo "Info: NFS umount skipped: a borg is still using /backup"
    exit 0
fi

umount -f -l /backup

if grep -qs "$BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER" /proc/mounts; then
    echo "ERROR!!! UNABLE TO UNMOUNT /backup $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
    exit 1
else
    echo "BACKUP NFS UnMOUNTED"
fi
