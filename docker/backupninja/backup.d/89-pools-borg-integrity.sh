#!/bin/bash

BACKUP_TYPE="pools"
BACKUP_WHEN_VAR="BACKUP_POOLS_WHEN"
MIN_FILES=1
MIN_SIZE=500

source /usr/local/bin/borg_integrity_template.sh
