#!/bin/sh
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes

if   [ "$2" = "db" ]; then
    BACKUP_PATH="/backup/db"
elif [ "$2" = "disks" ]; then
    BACKUP_PATH="/backup/disks"
else
    echo "The second parameter should be db or disks"
    exit 1
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
    borg extract --dry-run --list $BACKUP_PATH::$3
elif [ "$1" == "list" ]; then
    borg list --short $BACKUP_PATH
elif [ "$1" == "info" ]; then
    borg info $BACKUP_PATH
elif [ "$1" == "show-files" ]; then
    borg list --short $BACKUP_PATH::$3
elif [ "$1" == "extract" ]; then
    cd /backup/extract && borg extract --list $BACKUP_PATH::$3 $4
elif [ "$1" == "execute-now" ]; then
    if [ "$2" = "db" ]; then
        rm /dbdump/isard-db*.tar.gz
        nice -n 0 \
        /usr/bin/rethinkdb-dump -c "isard-db:28015" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"

        nice -n 0 \
        borg create --stats --compression lz4  \
        $BACKUP_PATH::{now:%Y-%m-%dT%H:%M:%S}  \
        /dbdump
    fi

    if [ "$2" = "disks" ]; then
        nice -n 0 \
        borg create --stats --compression lz4  \
        $BACKUP_PATH::{now:%Y-%m-%dT%H:%M:%S}  \
        $BACKUP_DISKS_TEMPLATES_ENABLED $BACKUP_DISKS_GROUPS_ENABLED $BACKUP_DISKS_MEDIA_ENABLED
    fi
fi