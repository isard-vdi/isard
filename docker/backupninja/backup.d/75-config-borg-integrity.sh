#!/bin/bash
#
# Configuration Borg Integrity Verifier
# Performs comprehensive integrity checks to determine final backup success/failure status
# This is the authoritative verification that the backup is recoverable and valid
#

# Set backup type specific variables
BACKUP_TYPE="config"
BACKUP_WHEN_VAR="BACKUP_CONFIG_WHEN"
MIN_FILES=10  # Config backup should have multiple files
MIN_SIZE=1024  # Minimum 1KB for development environment (relaxed from 100KB)

# Source the common integrity template
source /usr/local/bin/borg_integrity_template.sh