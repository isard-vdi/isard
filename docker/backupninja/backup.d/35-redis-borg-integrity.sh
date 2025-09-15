#!/bin/bash
#
# Redis Borg Integrity Verifier
# Performs comprehensive integrity checks to determine final backup success/failure status
# This is the authoritative verification that the backup is recoverable and valid
#

# Set backup type specific variables
BACKUP_TYPE="redis"
BACKUP_WHEN_VAR="BACKUP_REDIS_WHEN"
MIN_FILES=1  # Redis backup should have at least 1 file
MIN_SIZE=1024  # Minimum 1KB

# Source the common integrity template
source /usr/local/bin/borg_integrity_template.sh