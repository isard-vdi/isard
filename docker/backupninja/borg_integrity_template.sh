#!/bin/bash
#
# Generic Borg Backup Integrity Verification Template
# This template performs comprehensive integrity checks and determines final backup success/failure status
# The integrity verification is the authoritative test of backup recoverability and validity
#
# Usage: Copy this file and set the following variables:
# - BACKUP_TYPE: "db", "redis", "stats", "config", "disks"
# - BACKUP_WHEN_VAR: Environment variable name for schedule (e.g., "BACKUP_DB_WHEN")
# - MIN_FILES: Minimum expected file count (0 for optional content)
# - MIN_SIZE: Minimum expected size in bytes
#

# Set these variables based on backup type:
BACKUP_TYPE="${BACKUP_TYPE:-unknown}"
BACKUP_WHEN_VAR="${BACKUP_WHEN_VAR:-BACKUP_${BACKUP_TYPE^^}_WHEN}"
MIN_FILES="${MIN_FILES:-1}"
MIN_SIZE="${MIN_SIZE:-1024}"

# Get backup configuration from environment
BACKUP_WHEN="${!BACKUP_WHEN_VAR:-disabled}"

# Only run if backup is enabled
if [ "$BACKUP_WHEN" = "disabled" ]; then
    exit 0
fi

REPO_PATH="/backup/$BACKUP_TYPE"
LOG_PREFIX="BORG_STATS_${BACKUP_TYPE^^}"
LOG_FILE="${LOG_FILE:-/var/log/backupninja.log}"

# Redirect all output to both stdout and log file
exec > >(tee -a "$LOG_FILE")

# Check if repository exists
if [ ! -d "$REPO_PATH" ]; then
    echo "$(date '+%b %d %H:%M:%S') Warning: $BACKUP_TYPE borg repository not found at $REPO_PATH"
    exit 0
fi

# Set up borg environment
export BORG_PASSPHRASE=""
export BORG_RELOCATED_REPO_ACCESS_IS_OK="yes"
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK="yes"

echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Collecting statistics for $BACKUP_TYPE backup"

# Get repository info
REPO_INFO=$(borg info "$REPO_PATH" --json 2>/dev/null)
if [ $? -eq 0 ]; then
    REPO_ID=$(echo "$REPO_INFO" | jq -r '.repository.id // "unknown"')
    echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Repository ID: ${REPO_ID:0:16}..."
fi

# Initialize validation status
VALIDATION_STATUS="✓ PASSED"
VALIDATION_ISSUES=""
INTEGRITY_CHECK_EXIT=0

# Get list of archives and find the most recent one
ARCHIVES=$(borg list "$REPO_PATH" --json 2>/dev/null)
if [ $? -eq 0 ]; then
    LATEST_ARCHIVE=$(echo "$ARCHIVES" | jq -r '.archives | last | .name // empty')
    if [ -n "$LATEST_ARCHIVE" ]; then
        echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Latest archive: $LATEST_ARCHIVE"
        
        # Verify today's backup exists
        TODAY=$(date '+%Y-%m-%d')
        LATEST_DATE=$(echo "$LATEST_ARCHIVE" | cut -d'T' -f1)
        
        if [ "$LATEST_DATE" = "$TODAY" ]; then
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: ✓ Today's backup confirmed ($LATEST_DATE)"
        else
            echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: ✗ INTEGRITY ALERT: Latest backup is not from today (latest: $LATEST_DATE, expected: $TODAY)"
        fi
        
        # Perform comprehensive integrity check (both repository and archives)
        echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Performing comprehensive integrity check..."
        INTEGRITY_CHECK=$(borg check "$REPO_PATH" 2>&1)
        INTEGRITY_CHECK_EXIT=$?
        
        if [ $INTEGRITY_CHECK_EXIT -eq 0 ]; then
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: ✓ Repository and archive integrity check passed"
        else
            echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: ✗ INTEGRITY ALERT: Integrity check failed: $INTEGRITY_CHECK"
        fi
        
        # Get detailed statistics for the latest archive
        ARCHIVE_INFO=$(borg info "$REPO_PATH::$LATEST_ARCHIVE" --json 2>/dev/null)
        if [ $? -eq 0 ]; then
            # Extract statistics
            NFILES=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.nfiles // 0')
            ORIGINAL_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.original_size // 0')
            COMPRESSED_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.compressed_size // 0')
            DEDUPLICATED_SIZE=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].stats.deduplicated_size // 0')
            
            # Extract timing information
            START_TIME=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].start // "unknown"')
            END_TIME=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].end // "unknown"')
            DURATION=$(echo "$ARCHIVE_INFO" | jq -r '.archives[0].duration // 0')
            
            # Validate backup content
            VALIDATION_STATUS="✓ PASSED"
            VALIDATION_ISSUES=""
            
            # Check minimum file count
            if [ "$NFILES" -lt "$MIN_FILES" ]; then
                if [ "$MIN_FILES" -eq 0 ]; then
                    VALIDATION_STATUS="⚠ WARNING"
                    VALIDATION_ISSUES="$VALIDATION_ISSUES No files in backup (may be normal); "
                else
                    VALIDATION_STATUS="✗ FAILED"
                    VALIDATION_ISSUES="$VALIDATION_ISSUES Too few files ($NFILES < $MIN_FILES); "
                fi
            fi
            
            # Check minimum size
            if [ "$DEDUPLICATED_SIZE" -lt "$MIN_SIZE" ]; then
                if [ "$NFILES" -eq 0 ]; then
                    VALIDATION_STATUS="⚠ WARNING"
                    VALIDATION_ISSUES="$VALIDATION_ISSUES Empty backup; "
                else
                    VALIDATION_STATUS="✗ FAILED"
                    VALIDATION_ISSUES="$VALIDATION_ISSUES Backup too small ($DEDUPLICATED_SIZE < $MIN_SIZE bytes); "
                fi
            fi
            
            # Check if backup completed recently (within last 24 hours)
            if [ "$END_TIME" != "unknown" ]; then
                END_TIMESTAMP=$(date -d "$END_TIME" +%s 2>/dev/null || echo "0")
                CURRENT_TIMESTAMP=$(date +%s)
                TIME_DIFF=$((CURRENT_TIMESTAMP - END_TIMESTAMP))
                
                if [ $TIME_DIFF -gt 86400 ]; then
                    VALIDATION_STATUS="✗ FAILED"
                    VALIDATION_ISSUES="$VALIDATION_ISSUES Backup older than 24h; "
                fi
            fi
            
            # Calculate efficiency ratio
            EFFICIENCY="N/A"
            if [ "$ORIGINAL_SIZE" -gt 0 ] && [ "$DEDUPLICATED_SIZE" -gt 0 ]; then
                EFFICIENCY=$(echo "scale=2; $ORIGINAL_SIZE / $DEDUPLICATED_SIZE" | bc -l 2>/dev/null || echo "N/A")
            fi
            
            # Format sizes for human readability
            ORIGINAL_SIZE_H=$(numfmt --to=iec --suffix=B $ORIGINAL_SIZE 2>/dev/null || echo "${ORIGINAL_SIZE}B")
            COMPRESSED_SIZE_H=$(numfmt --to=iec --suffix=B $COMPRESSED_SIZE 2>/dev/null || echo "${COMPRESSED_SIZE}B")
            DEDUPLICATED_SIZE_H=$(numfmt --to=iec --suffix=B $DEDUPLICATED_SIZE 2>/dev/null || echo "${DEDUPLICATED_SIZE}B")
            
            # Format duration for human readability
            DURATION_H=$(printf "%.3fs" "$DURATION" 2>/dev/null || echo "${DURATION}s")
            
            # Output structured statistics to logs with appropriate severity
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: === BORG BACKUP VERIFICATION ==="
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Repository: $REPO_PATH"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Archive: $LATEST_ARCHIVE"
            
            # Log validation status with appropriate severity
            if [[ "$VALIDATION_STATUS" == *"FAILED"* ]]; then
                echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: INTEGRITY ALERT: Validation: $VALIDATION_STATUS"
                [ -n "$VALIDATION_ISSUES" ] && echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: INTEGRITY ISSUES: $VALIDATION_ISSUES"
            elif [[ "$VALIDATION_STATUS" == *"WARNING"* ]]; then
                echo "$(date '+%b %d %H:%M:%S') Warning: $LOG_PREFIX: Validation: $VALIDATION_STATUS"
                [ -n "$VALIDATION_ISSUES" ] && echo "$(date '+%b %d %H:%M:%S') Warning: $LOG_PREFIX: Issues: $VALIDATION_ISSUES"
            else
                echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Validation: $VALIDATION_STATUS"
            fi
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: --- TIMING ---"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Start time: $START_TIME"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: End time: $END_TIME"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Duration: $DURATION_H"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: --- CONTENT ---"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Files: $NFILES"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Original size: $ORIGINAL_SIZE_H ($ORIGINAL_SIZE bytes)"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Compressed size: $COMPRESSED_SIZE_H ($COMPRESSED_SIZE bytes)"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Deduplicated size: $DEDUPLICATED_SIZE_H ($DEDUPLICATED_SIZE bytes)"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: Deduplication efficiency: ${EFFICIENCY}x"
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: === END VERIFICATION ==="
            
            # Output raw JSON for parsing (single line for easy parsing)
            echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: STATS_JSON: $(echo "$ARCHIVE_INFO" | jq -c '.archives[0]')"
            
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

# Exit with appropriate code based on integrity check results
# This determines the final backup success/failure status
if [ $INTEGRITY_CHECK_EXIT -ne 0 ]; then
    echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: BACKUP FAILED: Repository integrity check failed"
    exit 1
fi

if [[ "$VALIDATION_STATUS" == *"FAILED"* ]]; then
    echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: BACKUP FAILED: Content validation failed"
    exit 1
fi

# Check if today's backup exists 
TODAY=$(date '+%Y-%m-%d')
if [ -n "$LATEST_ARCHIVE" ]; then
    LATEST_DATE=$(echo "$LATEST_ARCHIVE" | cut -d'T' -f1)
    if [ "$LATEST_DATE" != "$TODAY" ]; then
        echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: BACKUP FAILED: No recent backup found (latest: $LATEST_DATE)"
        exit 1
    fi
else
    echo "$(date '+%b %d %H:%M:%S') Error: $LOG_PREFIX: BACKUP FAILED: No archives found in repository"
    exit 1
fi

echo "$(date '+%b %d %H:%M:%S') Info: $LOG_PREFIX: BACKUP VERIFIED: All integrity checks passed"
exit 0
