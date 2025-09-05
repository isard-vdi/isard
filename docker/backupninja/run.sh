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
export LOG_FILE
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

# Export empty variable for envsubst template processing
export my_empty_variable=""

#
# DB
#
if [ "$BACKUP_DB_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "DATABASE ENABLED: Enabled database backup $BACKUP_DB_WHEN with $BACKUP_DB_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    template_jobs="10-db-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 11-db-nfs-mount.sh"
    template_jobs="$template_jobs 12-db-dump.sh 13-db-borg.borg 14-db-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 19-db-nfs-umount.sh"
    
    static_jobs="15-db-borg-stats.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
    
    for job in $static_jobs; do
        cp "/usr/local/share/backup.d/$job" "/usr/local/etc/backup.d/$job"
        # Add when clause to static jobs so they get scheduled
        sed -i "1a\\when = $BACKUP_DB_WHEN" "/usr/local/etc/backup.d/$job"
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

    template_jobs="20-redis-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 21-redis-nfs-mount.sh"
    template_jobs="$template_jobs 22-redis-dump.sh 23-redis-borg.borg 24-redis-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 29-redis-nfs-umount.sh"
    
    static_jobs="25-redis-borg-stats.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
    
    for job in $static_jobs; do
        cp "/usr/local/share/backup.d/$job" "/usr/local/etc/backup.d/$job"
        # Add when clause to static jobs so they get scheduled
        sed -i "1a\\when = $BACKUP_REDIS_WHEN" "/usr/local/etc/backup.d/$job"
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

    template_jobs="30-stats-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 31-stats-nfs-mount.sh"
    template_jobs="$template_jobs 32-stats-dump.sh 33-stats-borg.borg 34-stats-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 39-stats-nfs-umount.sh"
    
    static_jobs="35-stats-borg-stats.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
    
    for job in $static_jobs; do
        cp "/usr/local/share/backup.d/$job" "/usr/local/etc/backup.d/$job"
        # Add when clause to static jobs so they get scheduled
        sed -i "1a\\when = $BACKUP_STATS_WHEN" "/usr/local/etc/backup.d/$job"
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

    template_jobs="80-config-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 81-config-nfs-mount.sh"
    template_jobs="$template_jobs 82-config-borg.borg 84-config-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 89-config-nfs-umount.sh"
    
    static_jobs="85-config-borg-stats.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
    
    for job in $static_jobs; do
        cp "/usr/local/share/backup.d/$job" "/usr/local/etc/backup.d/$job"
        # Add when clause to static jobs so they get scheduled
        sed -i "1a\\when = $BACKUP_CONFIG_WHEN" "/usr/local/etc/backup.d/$job"
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


    template_jobs="90-disks-info.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 91-disks-nfs-mount.sh"
    template_jobs="$template_jobs 92-disks-borg.borg 94-disks-compact.sh"
    [ "$BACKUP_NFS_ENABLED" = "true" ] && template_jobs="$template_jobs 99-disks-nfs-umount.sh"
    
    static_jobs="95-disks-borg-stats.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "/usr/local/etc/backup.d/$job"
    done
    
    for job in $static_jobs; do
        cp "/usr/local/share/backup.d/$job" "/usr/local/etc/backup.d/$job"
        # Add when clause to static jobs so they get scheduled
        sed -i "1a\\when = $BACKUP_DISKS_WHEN" "/usr/local/etc/backup.d/$job"
    done
fi

# Add session start and end markers for automated backups based on 'when' schedules
ENABLED_WHEN_SCHEDULES=""
[ "$BACKUP_DB_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_DB_WHEN"
[ "$BACKUP_REDIS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_REDIS_WHEN"
[ "$BACKUP_STATS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_STATS_WHEN"
[ "$BACKUP_CONFIG_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_CONFIG_WHEN"
[ "$BACKUP_DISKS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_DISKS_WHEN"

# Get unique when schedules (preserve whole phrases using | as delimiter)
UNIQUE_SCHEDULES=$(echo "$ENABLED_WHEN_SCHEDULES" | tr '|' '\n' | grep -v "^$" | sort -u | grep -v "disabled")

# Create session start marker for automated backups if any schedules are enabled
if [ -n "$UNIQUE_SCHEDULES" ] && [ "$UNIQUE_SCHEDULES" != "" ]; then
    # Create a single start marker script for all automated backups
    START_SCRIPT="/usr/local/etc/backup.d/1-backup-start.sh"
    # Extract the first schedule for the start marker (they should all be the same anyway)
    FIRST_SCHEDULE=$(echo "$UNIQUE_SCHEDULES" | head -n1)
    cat > "$START_SCRIPT" << EOF
#!/bin/sh
# Add backup session start marker for automated backups
LOG_FILE="/var/log/backupninja.log"
echo "\$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_START: automated full backup initiated by cron (schedule: $FIRST_SCHEDULE)" >> \$LOG_FILE
EOF
    chmod 700 "$START_SCRIPT"
    
    # Set the schedule for the start marker to match enabled backups
    if [ "$BACKUP_DB_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_DB_WHEN" "$START_SCRIPT"
    elif [ "$BACKUP_REDIS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_REDIS_WHEN" "$START_SCRIPT"
    elif [ "$BACKUP_STATS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_STATS_WHEN" "$START_SCRIPT"
    elif [ "$BACKUP_CONFIG_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_CONFIG_WHEN" "$START_SCRIPT"
    elif [ "$BACKUP_DISKS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_DISKS_WHEN" "$START_SCRIPT"
    fi
    
    # Copy the reporting script as a static job for automated backups
    cp "/usr/local/share/backup.d/99-send-backup-report.sh" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    chmod 700 "/usr/local/etc/backup.d/99-send-backup-report.sh"
    
    # Set the schedule for the reporting script to match any enabled backup
    if [ "$BACKUP_DB_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_DB_WHEN" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    elif [ "$BACKUP_REDIS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_REDIS_WHEN" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    elif [ "$BACKUP_STATS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_STATS_WHEN" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    elif [ "$BACKUP_CONFIG_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_CONFIG_WHEN" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    elif [ "$BACKUP_DISKS_ENABLED" = "true" ]; then
        sed -i "1a\\when = $BACKUP_DISKS_WHEN" "/usr/local/etc/backup.d/99-send-backup-report.sh"
    fi
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
            # Exclude the reporting script from manual execution to avoid duplicate reports
            find /usr/local/etc/backup.d -name "$1" | grep -v "99-send-backup-report" | sort | xargs -I% backupninja --run % --now
        }

        # Add backup session start marker
        echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_START: manual $2 backup initiated by user" >> "$LOG_FILE"
        
        backup_args "$2"
        execute_now "$BACKUP_SCRIPTS_PREFIX"
        
        # Add backup session end marker
        echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_END: manual $2 backup completed" >> "$LOG_FILE"
        
        # Send backup report to API after manual execution
        echo "Sending backup report to API..."
        export BACKUP_TYPE="manual"
        python3 /usr/local/bin/backup_report.py
        ;;

    "execute-now-all")
        execute_now() {
            # Exclude the reporting script from manual execution to avoid duplicate reports
            find /usr/local/etc/backup.d -name "$1" | grep -v "99-send-backup-report" | sort | xargs -I% backupninja --run % --now
        }
        
        # Add backup session start marker for all backups
        echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_START: manual full backup initiated by user" >> "$LOG_FILE"
        
        for backup_type in "db" "redis" "stats" "config" "disks"; do
            backup_args "$backup_type"
            execute_now "$BACKUP_SCRIPTS_PREFIX"
        done
        
        # Add backup session end marker
        echo "$(date '+%b %d %H:%M:%S') Info: BACKUP_SESSION_END: manual full backup completed" >> "$LOG_FILE"
        
        # Send backup report to API after manual execution of full backup
        echo "Sending backup report to API..."
        export BACKUP_TYPE="manual"
        python3 /usr/local/bin/backup_report.py
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

