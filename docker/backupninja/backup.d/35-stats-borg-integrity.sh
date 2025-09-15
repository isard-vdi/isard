#!/bin/bash
#
# Stats Borg Integrity Verifier
# Performs comprehensive integrity checks to determine final backup success/failure status
# This is the authoritative verification that the backup is recoverable and valid
#

# Set backup type specific variables
BACKUP_TYPE="stats"
BACKUP_WHEN_VAR="BACKUP_STATS_WHEN"
MIN_FILES=0  # Stats backup may be empty
MIN_SIZE=100  # Minimum 100 bytes if files exist

# Source the common integrity template
source /usr/local/bin/borg_integrity_template.sh
