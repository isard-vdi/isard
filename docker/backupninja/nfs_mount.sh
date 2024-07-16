#!/bin/sh

mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "BACKUP NFS FOLDER MOUNTED: $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
else
    echo "ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER !!!"
    exit 1
fi