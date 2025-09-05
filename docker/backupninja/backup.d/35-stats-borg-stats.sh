#!/bin/bash
#
# Stats Borg Statistics Reporter
# Outputs detailed statistics for the just-completed stats borg backup
#

# Get backup configuration from environment
BACKUP_WHEN="${BACKUP_STATS_WHEN:-disabled}"

# Only run if stats backup is enabled
if [ "$BACKUP_WHEN" = "disabled" ]; then
    exit 0
fi

REPO_PATH="/backup/stats"
LOG_PREFIX="BORG_STATS_STATS"
LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"

# Redirect all output to both stdout and log file
exec > >(tee -a "$LOG_FILE")

# Check if repository exists
if [ ! -d "$REPO_PATH" ]; then
    echo "$(date '+%b %d %H:%M:%S') Warning: Stats borg repository not found at $REPO_PATH"
    exit 0
fi

# Set up borg environment
export BORG_PASSPHRASE=""
export BORG_RELOCATED_REPO_ACCESS_IS_OK="yes"
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK="yes"

echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Collecting statistics for stats backup"

# Get repository info
REPO_INFO=$(borg info "$REPO_PATH" --json 2>/dev/null)
if [ $? -eq 0 ]; then
    REPO_ID=$(echo "$REPO_INFO" | jq -r '.repository.id // "unknown"')
    echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Repository ID: ${REPO_ID:0:16}..."
fi

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