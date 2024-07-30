#!/bin/sh

umount -f -l /backup

if grep -qs "$BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER" /proc/mounts; then
    echo "ERROR!!! UNABLE TO UNMOUNT /backup $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
    exit 1
else
    echo "BACKUP NFS UnMOUNTED"
fi
