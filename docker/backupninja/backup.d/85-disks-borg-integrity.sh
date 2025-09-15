#!/bin/bash
#
# Disks Borg Integrity Verifier
# Performs comprehensive integrity checks to determine final backup success/failure status
# This is the authoritative verification that the backup is recoverable and valid
#

# Set backup type specific variables
BACKUP_TYPE="disks"
BACKUP_WHEN_VAR="BACKUP_DISKS_WHEN"
MIN_FILES=1  # Disks backup should have at least 1 file (varies by content)
MIN_SIZE=500  # Minimum 500B for development environment (relaxed from 1MB)

# Source the common integrity template
source /usr/local/bin/borg_integrity_template.sh