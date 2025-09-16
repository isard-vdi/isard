# Move Disks - Storage Migration Tool

## Overview

The `move_disks` script is a bilateral storage migration tool for IsardVDI that automatically moves VM disk files between fast and slow storage pools based on file modification dates. This implements intelligent storage tiering to optimize performance and cost.

## What We Implemented

Converted the hardcoded storage migration script to use flexible CLI parameters, making it configurable for different environments and use cases. The script now supports both absolute and relative date filtering, customizable threading, bandwidth limiting, and dry-run capabilities.

## Migration Logic

- **Fast→Slow**: Files older than the date threshold are moved from fast storage to slow storage
- **Slow→Fast**: Files newer than the date threshold are moved from slow storage to fast storage
- **Threading**: Concurrent processing with configurable worker counts for each direction
- **Safety**: Validates storage status, handles errors gracefully, and logs all operations

## Command Line Parameters

### Storage Pool Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--fast-pool` | `fast` | Name of the fast storage pool |
| `--slow-pool` | `vdo3` | Name of the slow storage pool |

### Date Filtering (Mutually Exclusive)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--filter-date` | - | Absolute date threshold (ISO format: YYYY-MM-DDTHH:MM:SS) |
| `--past-days` | - | Relative date threshold (number of days ago from today) |
| **Default behavior** | 30 days ago | Used when neither option is specified |

### Threading Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--threads-fast-to-slow` | `4` | Number of threads for moving old files fast→slow (0 to disable) |
| `--threads-slow-to-fast` | `3` | Number of threads for moving recent files slow→fast (0 to disable) |

### Performance Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--bandwidth-limit` | `200000` | Bandwidth limit in KB/s (0 for unlimited) |
| `--rsync-timeout` | `3600` | Timeout in seconds for rsync operations |
| `--startup-delay` | `10` | Seconds to wait before starting processing |

### Utility Options

| Parameter | Description |
|-----------|-------------|
| `--list-pools` | Show available storage pools and exit |
| `--dry-run` | Preview migration plan without executing |
| `--no-cleanup` | Skip cleanup of bad files logs at startup |
| `--help` | Show help message and exit |

## Usage Examples

### Basic Usage

```bash
# Use defaults (30 days ago threshold)
./move_disks

# Show help
./move_disks --help

# List available storage pools
./move_disks --list-pools
```

### Date Filtering

```bash
# Move files older than 5 days to slow storage
./move_disks --past-days 5

# Move files older than 30 days to slow storage
./move_disks --past-days 30

# Use absolute date threshold
./move_disks --filter-date 2024-01-01T00:00:00

# Use specific date and time
./move_disks --filter-date 2024-06-15T12:00:00
```

### Custom Storage Pools

```bash
# Custom pools with 7-day threshold
./move_disks --fast-pool ssd --slow-pool hdd --past-days 7

# Different pools with absolute date
./move_disks --fast-pool nvme --slow-pool archive --filter-date 2024-01-01T00:00:00
```

### Performance Tuning

```bash
# Limited bandwidth and threading
./move_disks --past-days 30 --threads-fast-to-slow 2 --bandwidth-limit 100000

# High performance settings
./move_disks --past-days 7 --threads-fast-to-slow 8 --threads-slow-to-fast 6 --bandwidth-limit 0

# Disable one direction (only move old files to slow storage)
./move_disks --past-days 30 --threads-slow-to-fast 0

# Long timeout for large files
./move_disks --past-days 14 --rsync-timeout 7200
```

### Testing and Preview

```bash
# Preview migration for 14-day threshold (no actual moves)
./move_disks --dry-run --past-days 14

# Preview with specific pools
./move_disks --dry-run --fast-pool ssd --slow-pool hdd --past-days 7

# Skip startup cleanup for testing
./move_disks --no-cleanup --dry-run --past-days 5
```

### Production Examples

```bash
# Conservative daily migration (1 week threshold, limited threads)
./move_disks --past-days 7 --threads-fast-to-slow 2 --threads-slow-to-fast 2

# Aggressive optimization (3 days threshold, full performance)
./move_disks --past-days 3 --threads-fast-to-slow 6 --threads-slow-to-fast 4

# Maintenance mode (move very old files, no recent file moves)
./move_disks --past-days 90 --threads-slow-to-fast 0 --bandwidth-limit 50000
```

## Error Handling and Logging

The script creates timestamped log files in `/logs/` for different scenarios:

- `move_disks-TIMESTAMP-moved_to_pool.json` - Successfully moved files
- `move_disks-TIMESTAMP-non_existing_in_db.json` - Files not found in database
- `move_disks-TIMESTAMP-not_ready.json` - Storage/domain not ready for migration
- `move_disks-TIMESTAMP-recycled_storage.json` - Files with recycled status
- `move_disks-TIMESTAMP-failed_to_move_to_pool.json` - Migration failures
- `move_disks-TIMESTAMP-non_valid_qcow_files.json` - Invalid QCOW2 files
- `move_disks-TIMESTAMP-files_with_no_domains.json` - Files with no associated domains

## Safety Features

- **Graceful shutdown**: CTRL+C handling with thread cleanup
- **Validation**: Checks storage pool existence and status before migration
- **Dry-run mode**: Preview migrations without executing
- **Status checking**: Waits for storage/domain to be ready before moving
- **Error recovery**: Comprehensive error logging and handling
- **File validation**: Ensures files are valid QCOW2 images before processing

## Cron Configuration Examples

### Multi-Schedule Configuration

For production environments, consider multiple cron jobs with different schedules and parameters:

```bash
# Storage migration cron jobs for IsardVDI
# Runs daily at different times to balance load and optimize storage tiering

# PATH environment for cron
PATH=/usr/lib/sysstat:/usr/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# Daily storage migration - move files older than 7 days to slow storage
# Runs at 11:59 PM with conservative threading and bandwidth limits
59 23 * * * root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 7 --threads-fast-to-slow 2 --threads-slow-to-fast 2 --bandwidth-limit 100000 >> /var/log/isard-storage.move_disks.$(date +\%Y-\%m-\%d).log 2>&1

# Weekly aggressive migration - move files older than 30 days with higher performance
# Runs every Sunday at 2:00 AM when system load is typically low
0 2 * * 0 root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 30 --threads-fast-to-slow 4 --threads-slow-to-fast 3 --bandwidth-limit 200000 >> /var/log/isard-storage.move_disks.weekly.$(date +\%Y-\%m-\%d).log 2>&1

# Monthly deep archive - move very old files (90+ days) to slow storage only
# Runs on the 1st of each month at 3:00 AM, disables slow-to-fast migration
0 3 1 * * root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 90 --threads-fast-to-slow 3 --threads-slow-to-fast 0 --bandwidth-limit 50000 >> /var/log/isard-storage.move_disks.archive.$(date +\%Y-\%m-\%d).log 2>&1

# Log cleanup - remove old migration logs after 30 days
0 4 * * * root find /var/log -name "isard-storage.move_disks.*.log" -mtime +30 -delete

# Optional: Dry-run preview every Monday at 1:00 AM (for monitoring/alerting)
# 0 1 * * 1 root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --dry-run --past-days 7 >> /var/log/isard-storage.move_disks.preview.$(date +\%Y-\%m-\%d).log 2>&1
```

### Single Daily Job Configuration

For simpler setups, a single daily migration job:

```bash
# PATH environment for cron
PATH=/usr/lib/sysstat:/usr/sbin:/usr/sbin:/usr/bin:/sbin:/bin

# Daily storage migration - files older than 14 days with balanced settings
59 0 * * * root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 14 --threads-fast-to-slow 3 --threads-slow-to-fast 2 --bandwidth-limit 150000 >> /var/log/isard-storage.move_disks.$(date +\%Y-\%m-\%d).log 2>&1 && find /var/log -name "isard-storage.move_disks.*.log" -mtime +30 -delete
```

### Customization Examples

```bash
# High-frequency, conservative migration (every 6 hours)
0 */6 * * * root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 3 --threads-fast-to-slow 1 --bandwidth-limit 50000

# Low-frequency, aggressive migration (weekly)
0 2 * * 0 root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --past-days 30 --threads-fast-to-slow 6 --bandwidth-limit 0

# Custom storage pools
59 0 * * * root /usr/bin/docker exec -i isard-storage /opt/isard/move_disks --fast-pool nvme --slow-pool archive --past-days 7
```
