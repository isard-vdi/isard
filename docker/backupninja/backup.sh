#!/bin/sh
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes

mount_nfs(){
    if [ "$BACKUP_NFS_ENABLED" = "true" ]
    then
        mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
        if grep -qs '/backup ' /proc/mounts; then
            echo "BACKUP NFS FOLDER MOUNTED: $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
        else
            echo "ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER !!!"
            exit 1
        fi
    fi
}
umount_nfs(){
    if [ "$BACKUP_NFS_ENABLED" = "true" ]
    then
        if grep -qs '/backup ' /proc/mounts; then
            umount -f -l /backup
            echo "BACKUP NFS FOLDER UNMOUNTED"
        else
            echo "ERROR!!! UNABLE TO UNMOUNT"
            exit 1
        fi
    fi
}

if [ "$1" != "check-nfs-mount" ]; then
    if   [ "$2" = "db" ]; then
        BACKUP_PATH="/backup/db"
    elif [ "$2" = "disks" ]; then
        BACKUP_PATH="/backup/disks"
    else
        echo "The second parameter should be db or disks"
        exit 1
    fi
fi

## DISKS
if [ "$BACKUP_DISKS_TEMPLATES_ENABLED" = "false" ]; then
    BACKUP_DISKS_TEMPLATES_ENABLED=""
else
    BACKUP_DISKS_TEMPLATES_ENABLED="/opt/isard/templates"
fi
if [ "$BACKUP_DISKS_GROUPS_ENABLED" = "false" ]; then
    BACKUP_DISKS_GROUPS_ENABLED=""
else
    BACKUP_DISKS_GROUPS_ENABLED="/opt/isard/groups"
fi
if [ "$BACKUP_DISKS_MEDIA_ENABLED" = "false" ]; then
    BACKUP_DISKS_MEDIA_ENABLED=""
else
    BACKUP_DISKS_MEDIA_ENABLED="/opt/isard/media"
fi

if   [ "$1" == "check-integrity" ]; then
    mount_nfs
    borg extract --dry-run --list $BACKUP_PATH::$3
    umount_nfs
elif [ "$1" == "list" ]; then
    mount_nfs
    borg list --short $BACKUP_PATH
    umount_nfs
elif [ "$1" == "info" ]; then
    mount_nfs
    borg info $BACKUP_PATH
    umount_nfs
elif [ "$1" == "show-files" ]; then
    mount_nfs
    borg list --short $BACKUP_PATH::$3
    umount_nfs
elif [ "$1" == "extract" ]; then
    mount_nfs
    cd /backup/extract && borg extract --list $BACKUP_PATH::$3 $4
    umount_nfs
elif [ "$1" == "execute-now" ]; then
    if [ "$2" = "db" ]; then
        mount_nfs
        rm /dbdump/isard-db*.tar.gz
        nice -n 0 \
        /usr/bin/rethinkdb-dump -c "${RETHINKDB_HOST}:${RETHINKDB_PORT}" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"

        nice -n 0 \
        borg create --stats --compression lz4  \
        $BACKUP_PATH::{now:%Y-%m-%dT%H:%M:%S}  \
        /dbdump
        umount_nfs
    fi

    if [ "$2" = "disks" ]; then
        mount_nfs
        nice -n 0 \
        borg create --stats --compression lz4  \
        $BACKUP_PATH::{now:%Y-%m-%dT%H:%M:%S}  \
        $BACKUP_DISKS_TEMPLATES_ENABLED $BACKUP_DISKS_GROUPS_ENABLED $BACKUP_DISKS_MEDIA_ENABLED
        umount_nfs
    fi
elif [ "$1" == "check-nfs-mount" ]; then
    if [ "$BACKUP_NFS_ENABLED" = "true" ]
    then
        mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
        if grep -qs '/backup ' /proc/mounts; then
            echo "BACKUP NFS FOLDER MOUNTED:"
            cat /proc/mounts | grep "/backup"
        else
            echo "ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER !!!"
            exit 1
        fi
        umount -f -l /backup
        if grep -qs '/backup ' /proc/mounts; then
            df -h
            echo "ERROR!!! UNABLE TO UnMOUNT /backup"
            exit 1
        else
            echo "BACKUP NFS UnMOUNTED"
        fi
    else
        echo "Unable to check mount if BACKUP_NFS_ENABLED is not true"
    fi
fi
