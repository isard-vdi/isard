#!/bin/sh

set -e

mount_nfs() {
    if [ "$BACKUP_NFS_ENABLED" = "true" ]; then
        /usr/local/bin/nfs_mount.sh
    fi
}

umount_nfs() {
    if [ "$BACKUP_NFS_ENABLED" = "true" ]; then
        /usr/local/bin/nfs_umount.sh
    fi
}

# Prepare BackupNinja
LOG_FILE="/var/log/backupninja.log"
touch $LOG_FILE
sed -i '/^logfile =/d' /usr/local/etc/backupninja.conf
echo "logfile = $LOG_FILE" >> /usr/local/etc/backupninja.conf

# Prepare for backups
mkdir -p -m700 /usr/local/etc/backup.d
mkdir -p /usr/local/var/log
mkdir -p /backup
mkdir -p /dbdump
mkdir -p /redisdump

rm -f /usr/local/etc/backup.d/*

# NFS
mount_nfs

# Initialize backup repositories
mkdir -p /backup/db
borg init -e none /backup/db > /dev/null 2>&1 || true
mkdir -p /backup/redis
borg init -e none /backup/redis > /dev/null 2>&1 || true
mkdir -p /backup/stats
borg init -e none /backup/stats > /dev/null 2>&1 || true
mkdir -p /backup/config
borg init -e none /backup/config > /dev/null 2>&1 || true
mkdir -p /backup/disks
borg init -e none /backup/disks > /dev/null 2>&1 || true
mkdir -p /backup/extract

# Unmount if nfs as it will be mounted at backup cron time
umount_nfs

#
# DB
#
if [ "$BACKUP_DB_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "DATABASE ENABLED: Enabled database backup $BACKUP_DB_WHEN with $BACKUP_DB_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    jobs="10-db-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 11-db-nfs-mount.sh"
    jobs="$jobs 12-db-dump.sh 13-db-borg.borg 14-db-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 19-db-nfs-umount.sh"

    for job in $jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
fi

#
# Redis
#
if [ "$BACKUP_REDIS_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "REDIS ENABLED: Enabled redis backup $BACKUP_REDIS_WHEN with $BACKUP_REDIS_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    jobs="20-redis-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 21-redis-nfs-mount.sh"
    jobs="$jobs 22-redis-dump.sh 23-redis-borg.borg 24-redis-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 29-redis-nfs-umount.sh"

    for job in $jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
fi

#
# Stats
#
if [ "$BACKUP_STATS_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "STATS ENABLED: Enabled stats backup $BACKUP_STATS_WHEN with $BACKUP_STATS_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    jobs="30-stats-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 31-stats-nfs-mount.sh"
    jobs="$jobs 32-stats-dump.sh 33-stats-borg.borg 34-stats-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 39-stats-nfs-umount.sh"

    for job in $jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
fi

#
# Config
#
if [ "$BACKUP_CONFIG_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "CONFIG ENABLED: Enabled config backup $BACKUP_CONFIG_WHEN with $BACKUP_CONFIG_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    jobs="80-config-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 81-config-nfs-mount.sh"
    jobs="$jobs 82-config-borg.borg 84-config-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 89-config-nfs-umount.sh"

    for job in $jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
fi

#
# Disks
#
if [ "$BACKUP_DISKS_ENABLED" = "true" ]; then
    if [ "$BACKUP_DISKS_TEMPLATES_ENABLED" = "false" ]; then
        BACKUP_DISKS_TEMPLATES_ENABLED=""
    else
        BACKUP_DISKS_TEMPLATES_ENABLED="include = /opt/isard/templates"
    fi
    if [ "$BACKUP_DISKS_GROUPS_ENABLED" = "false" ]; then
        BACKUP_DISKS_GROUPS_ENABLED=""
    else
        BACKUP_DISKS_GROUPS_ENABLED="include = /opt/isard/groups"
    fi
    if [ "$BACKUP_DISKS_MEDIA_ENABLED" = "false" ]; then
        BACKUP_DISKS_MEDIA_ENABLED=""
    else
        BACKUP_DISKS_MEDIA_ENABLED="include = /opt/isard/media"
    fi

    if [ -z "$BACKUP_DISKS_TEMPLATES_ENABLED" ] && [ -z "$BACKUP_DISKS_GROUPS_ENABLED" ] && [ -z "$BACKUP_DISKS_MEDIA_ENABLED" ]; then
        echo "Error: All backup disk paths are disabled. Review your config. Exiting."
        exit 1
    fi


    if [ -z "$1" ]; then
        echo "DISKS ENABLED: Enabled disks backup $BACKUP_DISKS_WHEN with $BACKUP_DISKS_PRUNE prune policy"
        echo "               Disks backup included folders:"
        echo "               - TEMPLATES: $BACKUP_DISKS_TEMPLATES_ENABLED"
        echo "               -    GROUPS: $BACKUP_DISKS_GROUPS_ENABLED"
        echo "               -     MEDIA: $BACKUP_DISKS_MEDIA_ENABLED"
        echo "               Logs can be found at $LOG_FILE folder"
    fi


    jobs="90-disks-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 91-disks-nfs-mount.sh"
    jobs="$jobs 92-disks-borg.borg 94-disks-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && jobs="$jobs 99-disks-nfs-umount.sh"

    for job in $jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
fi

# Set correct permissions to the files
chmod 600 /usr/local/etc/backup.d/* > /dev/null 2>&1
chmod 700 /usr/local/etc/backup.d/*.sh > /dev/null 2>&1

backup_args() {
    case "$1" in
        "db")
            export BACKUP_SCRIPTS_PREFIX="1*"
            export BACKUP_PATH="/backup/db"
            ;;

        "redis")
            export BACKUP_SCRIPTS_PREFIX="2*"
            export BACKUP_PATH="/backup/redis"
            ;;

        "stats")
            export BACKUP_SCRIPTS_PREFIX="3*"
            export BACKUP_PATH="/backup/stats"
            ;;

        "config")
            export BACKUP_SCRIPTS_PREFIX="8*"
            export BACKUP_PATH="/backup/config"
            ;;

        "disks")
            export BACKUP_SCRIPTS_PREFIX="9*"
            export BACKUP_PATH="/backup/disks"
            ;;

        *)
            echo "Invalid backup option, must be 'db', 'redis', 'stats', 'config' or 'disks'"
            exit 1
            ;;
    esac
}

case "$1" in
    "execute-now")
        execute_now() {
            find /usr/local/etc/backup.d -name "$1" | sort | xargs -I% backupninja --run % --now
        }

        backup_args "$2"
        execute_now "$BACKUP_SCRIPTS_PREFIX"
        ;;

    "execute-now-all")
        execute_now() {
            find /usr/local/etc/backup.d -name "$1" | sort | xargs -I% backupninja --run % --now
        }
        for backup_type in "db" "redis" "stats" "config" "disks"; do
            backup_args "$backup_type"
            execute_now "$BACKUP_SCRIPTS_PREFIX"
        done
        ;;

    "list")
        mount_nfs
        backup_args "$2"

        borg list --short "$BACKUP_PATH"

        umount_nfs
        ;;

    "info")
        mount_nfs
        backup_args "$2"

        borg info "$BACKUP_PATH"

        umount_nfs
        ;;

    "show-files")
        mount_nfs
        backup_args "$2"
        if [ -z "$3" ]; then
            echo "Missing backup as last argument"
            exit 1
        fi

        borg list --short $BACKUP_PATH::$3

        umount_nfs
        ;;

    "check-integrity")
        mount_nfs
        backup_args "$2"
        if [ -z "$3" ]; then
            echo "Missing backup as last argument"
            exit 1
        fi

        borg extract --dry-run --list $BACKUP_PATH::$3

        umount_nfs
        ;;

    "extract")
        mount_nfs
        backup_args "$2"
        if [ -z "$3" ]; then
            echo "Missing backup as last argument"
            exit 1
        fi

        cd /backup/extract
        borg extract --list $BACKUP_PATH::$3 $4

        umount_nfs
        ;;

    "check-nfs-mount")
        mount_nfs
        umount_nfs
        ;;

    "")
        # Start the cron daemon and follow the logs
        crond
        tail -f $LOG_FILE
        ;;
    *)
        echo "Available commands"
        echo "      execute-now => run a backup"
        echo "      list => list all the backups"
        echo "      info => show info of a backup"
        echo "      show-files => show all the files of a backup"
        echo "      check-integrity => check a backup is extractable"
        echo "      extract => extract some files"
        echo "      check-nfs-mount => ensure the NFS can be mounted"
        exit 1
        ;;
esac

