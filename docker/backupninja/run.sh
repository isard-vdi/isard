#!/bin/sh

set -e

# Serialize the setup block with the 15-min self-heal cron so a self-heal
# tick cannot race the entrypoint (or a manual `run.sh setup`) on
# /usr/local/etc/backup.d{.staging,}/. The lock is released explicitly
# once setup finishes (see `exec 9>&-` below) so the entrypoint's
# `tail -f` doesn't keep it for the container's lifetime.
SETUP_LOCK="/var/lock/backupninja-setup.lock"
mkdir -p /var/lock
exec 9>"$SETUP_LOCK"
flock -n 9 || { echo "Setup already in progress; exiting."; exit 0; }

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

# Derive the `when` clause for a given type's integrity script.
# Args: <BACKUP_<TYPE>_WHEN value>
#   - If the backup doesn't touch Saturday -> "disabled" (no install)
#   - Else -> "saturday at HH[:MM]", reusing the backup's own time slot so
#     the integrity script runs in the same backupninja cron invocation as
#     the backup, right after it (alphabetic ordering within a slot:
#     25-*-integrity.sh runs after 24-*-compact.sh). The admin toggle is
#     evaluated live at script run time, not here.
integrity_when_for() {
    backup_when="$1"
    hhmm=$(echo "$backup_when" | sed -n 's/.*at[[:space:]]\+\([0-9]\{1,2\}\(:[0-9]\{2\}\)\?\).*/\1/p')
    if [ -z "$hhmm" ]; then
        echo "disabled"
        return
    fi
    case "$backup_when" in
        "everyday at"*|"saturday at"*) echo "saturday at $hhmm" ;;
        *)                             echo "disabled" ;;
    esac
}

# Return the scope name (db|redis|stats|config|disks|full) for a schedule
# string, based on which BACKUP_*_WHEN variables match it and are enabled.
scope_for_schedule() {
    schedule="$1"
    matches=""
    for kind in db redis stats config disks; do
        upper=$(echo "$kind" | tr '[:lower:]' '[:upper:]')
        eval enabled="\$BACKUP_${upper}_ENABLED"
        eval when="\$BACKUP_${upper}_WHEN"
        if [ "$enabled" = "true" ] && [ "$when" = "$schedule" ]; then
            matches="$matches $kind"
        fi
    done
    # strip leading space
    matches=$(echo "$matches" | sed 's/^ //')
    case "$(echo "$matches" | wc -w)" in
        0) echo "full" ;;
        1) echo "$matches" ;;
        *) echo "full" ;;
    esac
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
mkdir -p /var/log/backupninja.queue

# Stage all generated job files into a separate directory and only swap
# them into the live /usr/local/etc/backup.d/ at the end of setup. This
# way a partial setup (e.g. NFS unreachable at container start) cannot
# leave the live backup configuration empty: either the new staging set
# fully replaces the old one, or the old one stays in place untouched.
STAGING_DIR="/usr/local/etc/backup.d.staging"
rm -rf "$STAGING_DIR"
mkdir -p -m700 "$STAGING_DIR"

# NFS (with retry/backoff in nfs_mount.sh). If this fails after all
# retries the script aborts before touching /usr/local/etc/backup.d/ —
# leaving any previous-good config in place for the cron daemon to keep
# running once connectivity is restored.
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

    template_jobs="20-db-info.sh 22-db-dump.sh 23-db-borg.borg 24-db-compact.sh"

    static_jobs="25-db-borg-integrity.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "$STAGING_DIR/$job"
    done

    INTEGRITY_WHEN_DB="$(integrity_when_for "$BACKUP_DB_WHEN")"
    if [ "$INTEGRITY_WHEN_DB" != "disabled" ]; then
        for job in $static_jobs; do
            cp "/usr/local/share/backup.d/$job" "$STAGING_DIR/$job"
            sed -i "1a\\when = $INTEGRITY_WHEN_DB" "$STAGING_DIR/$job"
        done
    fi
fi

#
# Redis
#
if [ "$BACKUP_REDIS_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "REDIS ENABLED: Enabled redis backup $BACKUP_REDIS_WHEN with $BACKUP_REDIS_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    template_jobs="30-redis-info.sh 32-redis-dump.sh 33-redis-borg.borg 34-redis-compact.sh"

    static_jobs="35-redis-borg-integrity.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "$STAGING_DIR/$job"
    done

    INTEGRITY_WHEN_REDIS="$(integrity_when_for "$BACKUP_REDIS_WHEN")"
    if [ "$INTEGRITY_WHEN_REDIS" != "disabled" ]; then
        for job in $static_jobs; do
            cp "/usr/local/share/backup.d/$job" "$STAGING_DIR/$job"
            sed -i "1a\\when = $INTEGRITY_WHEN_REDIS" "$STAGING_DIR/$job"
        done
    fi
fi

#
# Stats
#
if [ "$BACKUP_STATS_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "STATS ENABLED: Enabled stats backup $BACKUP_STATS_WHEN with $BACKUP_STATS_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    template_jobs="40-stats-info.sh 42-stats-dump.sh 43-stats-borg.borg 44-stats-compact.sh"

    static_jobs="45-stats-borg-integrity.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "$STAGING_DIR/$job"
    done

    INTEGRITY_WHEN_STATS="$(integrity_when_for "$BACKUP_STATS_WHEN")"
    if [ "$INTEGRITY_WHEN_STATS" != "disabled" ]; then
        for job in $static_jobs; do
            cp "/usr/local/share/backup.d/$job" "$STAGING_DIR/$job"
            sed -i "1a\\when = $INTEGRITY_WHEN_STATS" "$STAGING_DIR/$job"
        done
    fi
fi

#
# Config
#
if [ "$BACKUP_CONFIG_ENABLED" = "true" ]; then
    if [ -z "$1" ]; then
        echo "CONFIG ENABLED: Enabled config backup $BACKUP_CONFIG_WHEN with $BACKUP_CONFIG_PRUNE prune policy"
        echo "                  Logs can be found at $LOG_FILE folder"
    fi

    template_jobs="70-config-info.sh 72-config-borg.borg 74-config-compact.sh"

    static_jobs="75-config-borg-integrity.sh"

    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "$STAGING_DIR/$job"
    done

    INTEGRITY_WHEN_CONFIG="$(integrity_when_for "$BACKUP_CONFIG_WHEN")"
    if [ "$INTEGRITY_WHEN_CONFIG" != "disabled" ]; then
        for job in $static_jobs; do
            cp "/usr/local/share/backup.d/$job" "$STAGING_DIR/$job"
            sed -i "1a\\when = $INTEGRITY_WHEN_CONFIG" "$STAGING_DIR/$job"
        done
    fi
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


    template_jobs="80-disks-info.sh 82-disks-borg.borg 84-disks-compact.sh"

    static_jobs="85-disks-borg-integrity.sh"

    # Re-assert STAGING_DIR in case a concurrent self_heal-triggered
    # `run.sh setup` removed it; install -D handles the same race for cp.
    mkdir -p -m700 "$STAGING_DIR"
    for job in $template_jobs; do
        envsubst < "/usr/local/share/backup.d/$job" > "$STAGING_DIR/$job"
    done

    INTEGRITY_WHEN_DISKS="$(integrity_when_for "$BACKUP_DISKS_WHEN")"
    if [ "$INTEGRITY_WHEN_DISKS" != "disabled" ]; then
        for job in $static_jobs; do
            install -D -m700 "/usr/local/share/backup.d/$job" "$STAGING_DIR/$job"
            sed -i "1a\\when = $INTEGRITY_WHEN_DISKS" "$STAGING_DIR/$job"
        done
    fi
fi

# Add session start and end markers for automated backups based on 'when' schedules
ENABLED_WHEN_SCHEDULES=""
[ "$BACKUP_DB_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_DB_WHEN"
[ "$BACKUP_REDIS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_REDIS_WHEN"
[ "$BACKUP_STATS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_STATS_WHEN"
[ "$BACKUP_CONFIG_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_CONFIG_WHEN"
[ "$BACKUP_DISKS_ENABLED" = "true" ] && ENABLED_WHEN_SCHEDULES="$ENABLED_WHEN_SCHEDULES|$BACKUP_DISKS_WHEN"

# Get unique when schedules (preserve whole phrases using | as delimiter)
UNIQUE_SCHEDULES=$(echo "$ENABLED_WHEN_SCHEDULES" | tr '|' '\n' | grep -v "^$" | sort -u | grep -v "disabled" || true)

# Create session start and end markers for each unique schedule. Use a
# here-doc into a temporary file so that SCHEDULE_INDEX increments in the
# current shell rather than a subshell spawned by a pipe.
SCHEDULE_INDEX=0
if [ -n "$UNIQUE_SCHEDULES" ]; then
    TMPFILE=$(mktemp)
    printf '%s\n' "$UNIQUE_SCHEDULES" >"$TMPFILE"
    while IFS= read -r SCHEDULE; do
        [ -n "$SCHEDULE" ] || continue

        SCOPE=$(scope_for_schedule "$SCHEDULE")

        # Re-assert STAGING_DIR in case it got wiped by a concurrent
        # `run.sh setup`; the flock above usually serializes us, this
        # is the belt-and-braces fallback.
        mkdir -p -m700 "$STAGING_DIR"

        # Start marker script for this schedule
        START_SCRIPT="$STAGING_DIR/10-session-start-$SCHEDULE_INDEX.sh"
        cat >"$START_SCRIPT" <<EOF
#!/bin/sh
# Add backup session start marker for automated backups (ISO-8601 timestamp)
LOG_FILE="/var/log/backupninja.log"
echo "\$(date '+%Y-%m-%dT%H:%M:%S') Info: BACKUP_SESSION_START: automated $SCOPE backup initiated by cron (schedule: $SCHEDULE)" >> \$LOG_FILE
EOF
        chmod 700 "$START_SCRIPT"
        sed -i "1a\\when = $SCHEDULE" "$START_SCRIPT"

        if [ "$BACKUP_NFS_ENABLED" = "true" ]; then
            NFS_MOUNT_SCRIPT="$STAGING_DIR/11-session-nfs-mount-$SCHEDULE_INDEX.sh"
            envsubst < "/usr/local/share/backup.d/05-session-nfs-mount.sh" > "$NFS_MOUNT_SCRIPT"
            chmod 700 "$NFS_MOUNT_SCRIPT"
            sed -i "1a\\when = $SCHEDULE" "$NFS_MOUNT_SCRIPT"
        fi

        # Preflight free-space check (runs after NFS mount so it sees the
        # real target). A FATAL here forces the eventual report to
        # CRITICAL even if no individual borg action fails.
        PREFLIGHT_SCRIPT="$STAGING_DIR/15-session-preflight-$SCHEDULE_INDEX.sh"
        install -D -m700 /usr/local/bin/session_preflight.sh "$PREFLIGHT_SCRIPT"
        chmod 700 "$PREFLIGHT_SCRIPT"
        sed -i "1a\\when = $SCHEDULE" "$PREFLIGHT_SCRIPT"

        END_SCRIPT="$STAGING_DIR/90-session-report-$SCHEDULE_INDEX.sh"
        cat >"$END_SCRIPT" <<EOF
#!/bin/sh
# Send backup report to API after automated backup completion
export BACKUP_TYPE="automated"
/usr/local/bin/send_backup_report.sh
EOF
        chmod 700 "$END_SCRIPT"
        sed -i "1a\\when = $SCHEDULE" "$END_SCRIPT"

        if [ "$BACKUP_NFS_ENABLED" = "true" ]; then
            NFS_UMOUNT_SCRIPT="$STAGING_DIR/91-session-nfs-umount-$SCHEDULE_INDEX.sh"
            envsubst < "/usr/local/share/backup.d/95-session-nfs-umount.sh" > "$NFS_UMOUNT_SCRIPT"
            chmod 700 "$NFS_UMOUNT_SCRIPT"
            sed -i "1a\\when = $SCHEDULE" "$NFS_UMOUNT_SCRIPT"
        fi

        SCHEDULE_INDEX=$((SCHEDULE_INDEX + 1))
    done <"$TMPFILE"
    rm -f "$TMPFILE"
fi

# Set correct permissions to the files
# Set correct permissions on the staged files before swapping in
chmod 600 $STAGING_DIR/* > /dev/null 2>&1
chmod 700 $STAGING_DIR/*.sh > /dev/null 2>&1

# Refuse to swap an empty staging set in: that would re-create the bug
# this whole atomic dance is meant to prevent. If for any reason no jobs
# were generated, leave the live config untouched and exit non-zero so
# the operator notices.
if [ -z "$(ls -A "$STAGING_DIR" 2>/dev/null)" ]; then
    echo "ERROR!!! No backup jobs generated in $STAGING_DIR; refusing to wipe live backup.d." >&2
    rmdir "$STAGING_DIR" 2>/dev/null || true
    exit 1
fi

# Atomic swap: only now do we wipe the live directory and replace it
# with the freshly-generated set. If we crash before this point, the
# live backup.d retains whatever it had before this run.
rm -f /usr/local/etc/backup.d/*
cp -a "$STAGING_DIR/." /usr/local/etc/backup.d/
rm -rf "$STAGING_DIR"
echo "BACKUPNINJA SETUP COMPLETE: $(ls -1 /usr/local/etc/backup.d/ | wc -l) job files installed"

# Release the setup lock: the entrypoint case below ends in `tail -f`
# which never exits, and we don't want to block subsequent `run.sh list`
# / `info` / self_heal probes for the lifetime of the container.
exec 9>&-

backup_args() {
    case "$1" in
        "db")
            export BACKUP_SCRIPTS_PREFIX="2*"
            export BACKUP_PATH="/backup/db"
            ;;

        "redis")
            export BACKUP_SCRIPTS_PREFIX="3*"
            export BACKUP_PATH="/backup/redis"
            ;;

        "stats")
            export BACKUP_SCRIPTS_PREFIX="4*"
            export BACKUP_PATH="/backup/stats"
            ;;

        "config")
            export BACKUP_SCRIPTS_PREFIX="7*"
            export BACKUP_PATH="/backup/config"
            ;;

        "disks")
            export BACKUP_SCRIPTS_PREFIX="8*"
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
            # Use || true to continue execution even if individual backups fail
            find /usr/local/etc/backup.d -name "$1" | grep -v "99-send-backup-report" | sort | while read -r script; do
                backupninja --run "$script" --now || true
            done
        }

        # Mount NFS if enabled
        mount_nfs

        # Add backup session start marker (ISO-8601 timestamp, scoped to arg)
        echo "$(date '+%Y-%m-%dT%H:%M:%S') Info: BACKUP_SESSION_START: manual $2 backup initiated by user" >> "$LOG_FILE"

        # Execute backup, continuing even if it fails
        backup_args "$2" || true
        execute_now "$BACKUP_SCRIPTS_PREFIX" || true

        # Add backup session end marker
        echo "$(date '+%Y-%m-%dT%H:%M:%S') Info: BACKUP_SESSION_END: manual $2 backup completed" >> "$LOG_FILE"

        # Force flush to ensure marker is written before parser reads
        sync

        # Send backup report to API after manual execution
        echo "Sending backup report to API..."
        export BACKUP_TYPE="manual"
        python3 /usr/local/bin/backup_report.py || echo "Warning: Failed to send backup report to API"

        # Unmount NFS if enabled
        umount_nfs
        ;;

    "execute-now-all")
        execute_now() {
            # Exclude the reporting script from manual execution to avoid duplicate reports
            # Use || true to continue execution even if individual backups fail
            find /usr/local/etc/backup.d -name "$1" | grep -v "99-send-backup-report" | sort | while read -r script; do
                backupninja --run "$script" --now || true
            done
        }

        # Mount NFS if enabled
        mount_nfs

        # Add backup session start marker for all backups (ISO-8601)
        echo "$(date '+%Y-%m-%dT%H:%M:%S') Info: BACKUP_SESSION_START: manual full backup initiated by user" >> "$LOG_FILE"

        # Execute all backup types, continuing even if individual ones fail
        for backup_type in "db" "redis" "stats" "config" "disks"; do
            backup_args "$backup_type" || true
            execute_now "$BACKUP_SCRIPTS_PREFIX" || true
        done

        # Add backup session end marker
        echo "$(date '+%Y-%m-%dT%H:%M:%S') Info: BACKUP_SESSION_END: manual full backup completed" >> "$LOG_FILE"

        # Force flush to ensure marker is written before parser reads
        sync

        # Send backup report to API after manual execution of full backup
        echo "Sending backup report to API..."
        export BACKUP_TYPE="manual"
        python3 /usr/local/bin/backup_report.py || echo "Warning: Failed to send backup report to API"

        # Unmount NFS if enabled
        umount_nfs
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

    "setup")
        # Setup phase already ran above (every invocation goes through it).
        # This command exists so the self-heal cron can re-run setup
        # explicitly without also starting crond / launching backups.
        # No-op past the setup block.
        echo "Setup-only run finished."
        ;;

    "")
        # Detect an orphaned session from a previous run (container was
        # killed or restarted mid-backup) and report it as CRITICAL before
        # we start serving the next cron tick. Non-fatal: any failure here
        # must not stop us from starting crond.
        /usr/local/bin/detect_orphaned_session.sh || true

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
