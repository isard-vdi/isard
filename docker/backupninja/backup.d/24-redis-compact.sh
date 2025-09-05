#!/bin/sh

when = $BACKUP_REDIS_WHEN

# Only run if redis backup is enabled
if [ "$when" = "disabled" ]; then
    exit 0
fi

REPO_PATH="/backup/redis"
LOG_PREFIX="BORG_STATS_REDIS"

# Check if today is Saturday (6)
if [ $(date +%u) -eq 6 ]; then
    # Check if the path exists
    if [ -d "/backup/redis" ]; then
        echo "Compacting Borg repository at /backup/redis..."
        borg compact --progress --cleanup-commits --verbose --threshold 5 "/backup/redis"
    fi
else
    echo "Today is not Saturday. Skipping the /backup/redis backup compacting."
fi

# Always collect borg statistics after backup (whether compacted or not)
if [ -d "$REPO_PATH" ]; then
    # Set up borg environment
    export BORG_PASSPHRASE=""
    export BORG_RELOCATED_REPO_ACCESS_IS_OK="yes"
    export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK="yes"

    echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Collecting statistics for redis backup"

    # Get list of archives and find the most recent one
    ARCHIVES=$(borg list "$REPO_PATH" --json 2>/dev/null)
    if [ $? -eq 0 ]; then
        LATEST_ARCHIVE=$(echo "$ARCHIVES" | jq -r '.archives | last | .name // empty')
        if [ -n "$LATEST_ARCHIVE" ]; then
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Latest archive: $LATEST_ARCHIVE"

            # Get detailed statistics for the latest archive
            ARCHIVE_INFO=$(borg info "$REPO_PATH::$LATEST_ARCHIVE" --json 2>/dev/null)
            if [ $? -eq 0 ]; then
                # Extract statistics
                NFILES=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.nfiles // 0')
                ORIGINAL_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.original_size // 0')
                COMPRESSED_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.compressed_size // 0')
                DEDUPLICATED_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.deduplicated_size // 0')

                # Calculate efficiency ratio
                EFFICIENCY="N/A"
                if [ "$ORIGINAL_SIZE" -gt 0 ] && [ "$DEDUPLICATED_SIZE" -gt 0 ]; then
                    EFFICIENCY=$(echo "scale=2; $ORIGINAL_SIZE / $DEDUPLICATED_SIZE" | bc -l 2>/dev/null || echo "N/A")
                fi

                # Format sizes for human readability
                ORIGINAL_SIZE_H=$(numfmt --to=iec --suffix=B $ORIGINAL_SIZE 2>/dev/null || echo "${ORIGINAL_SIZE}B")
                COMPRESSED_SIZE_H=$(numfmt --to=iec --suffix=B $COMPRESSED_SIZE 2>/dev/null || echo "${COMPRESSED_SIZE}B")
                DEDUPLICATED_SIZE_H=$(numfmt --to=iec --suffix=B $DEDUPLICATED_SIZE 2>/dev/null || echo "${DEDUPLICATED_SIZE}B")

                # Output structured statistics to logs
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: === BORG REPOSITORY STATISTICS ==="
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Repository: $REPO_PATH"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Archive: $LATEST_ARCHIVE"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Files: $NFILES"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Original size: $ORIGINAL_SIZE_H ($ORIGINAL_SIZE bytes)"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Compressed size: $COMPRESSED_SIZE_H ($COMPRESSED_SIZE bytes)"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Deduplicated size: $DEDUPLICATED_SIZE_H ($DEDUPLICATED_SIZE bytes)"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Deduplication efficiency: ${EFFICIENCY}x"
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: === END BORG STATISTICS ==="

                # Output raw JSON for parsing (single line for easy parsing)
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: STATS_JSON: $(echo "$ARCHIVE_INFO" | jq -c '.archives[0].stats')"

            else
                echo "$(date '+%b %d %H:%M:%S') Warning: $LOG_PREFIX: Could not get archive statistics for $LATEST_ARCHIVE"
            fi
        else
            echo "$(date '+%b %d %H:%M:%S') Warning: $LOG_PREFIX: No archives found in repository"
        fi
    else
        echo "$(date '+%b %d %H:%M:%S') Warning: $LOG_PREFIX: Could not list archives in repository"
    fi

    echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Statistics collection completed"
fi
