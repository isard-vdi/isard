#!/bin/bash
#
# Database Borg Integrity Verifier
# Performs comprehensive integrity checks to determine final backup success/failure status
# This is the authoritative verification that the backup is recoverable and valid
#

# Set backup type specific variables
BACKUP_TYPE="db"
BACKUP_WHEN_VAR="BACKUP_DB_WHEN"
MIN_FILES=1  # Database backup should have at least 1 file
MIN_SIZE=10240  # Minimum 10KB for database dumps

# Source the common integrity template
source /usr/local/bin/borg_integrity_template.sh