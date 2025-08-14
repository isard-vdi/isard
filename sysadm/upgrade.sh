#!/bin/bash

# Script lock mechanism to prevent concurrent executions
LOCK_FILE="/tmp/isardvdi-upgrade.lock"
LOCK_PID=""

# Function to acquire lock
acquire_lock() {
  if [ -f "$LOCK_FILE" ]; then
    local existing_pid
    existing_pid=$(cat "$LOCK_FILE" 2>/dev/null)
    
    # Check if process is still running
    if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "Error: Another upgrade process is already running (PID: $existing_pid)"
      echo "If this is incorrect, remove the lock file: $LOCK_FILE"
      exit 1
    else
      echo "Removing stale lock file..."
      rm -f "$LOCK_FILE"
    fi
  fi
  
  # Create lock file with current PID
  echo $$ > "$LOCK_FILE"
  LOCK_PID=$$
  echo "Acquired upgrade lock (PID: $$)"
}

# Function to release lock
release_lock() {
  if [ -n "$LOCK_PID" ] && [ -f "$LOCK_FILE" ]; then
    local lock_content
    lock_content=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ "$lock_content" = "$LOCK_PID" ]; then
      rm -f "$LOCK_FILE"
      echo "Released upgrade lock"
    fi
  fi
}

# Trap to ensure lock is released on exit
trap 'release_lock' EXIT INT TERM

# Function to update report with error status
update_report_error() {
  local error_msg="$1"
  if [ -n "$REPORT_FILE" ] && [ -f "$REPORT_FILE" ]; then
    cat >> "$REPORT_FILE" << EOF

## Upgrade Completion

**Status:** FAILED  
**Failed at:** $(date '+%Y-%m-%d %H:%M:%S')  
**Error:** $error_msg  

Upgrade failed and was aborted.
EOF
  fi
}

# Function to get the latest version from GitLab
get_latest_version() {
  echo "Fetching latest version from GitLab..." >&2
  local latest_version
  local api_response
  
  # Use curl with timeout and proper error handling
  api_response=$(curl -s --max-time 30 --retry 3 --retry-delay 2 \
    "https://gitlab.com/api/v4/projects/isard%2Fisardvdi/repository/tags" 2>/dev/null)
  
  # Check if curl succeeded
  if [ $? -ne 0 ] || [ -z "$api_response" ]; then
    echo "Error: Failed to fetch data from GitLab API" >&2
    exit 1
  fi
  
  # Check if response looks like valid JSON (basic check)
  if [[ ! "$api_response" =~ ^\[.*\]$ ]]; then
    echo "Error: Invalid response from GitLab API" >&2
    exit 1
  fi
  
  # Extract version using safer parsing
  latest_version=$(echo "$api_response" | \
    grep -o '"name":"v[^"]*"' | \
    head -1 | \
    sed 's/"name":"//; s/"//')
  
  if [ -z "$latest_version" ]; then
    echo "Error: Could not parse latest version from GitLab response" >&2
    exit 1
  fi
  
  # Validate version format (basic check for v followed by numbers and dots)
  if [[ ! "$latest_version" =~ ^v[0-9]+(\.[0-9]+)*$ ]]; then
    echo "Error: Invalid version format received: $latest_version" >&2
    exit 1
  fi
  
  echo "$latest_version"
}

# Function to check for major version changes
check_major_version_change() {
  local target_version="$1"
  local force_major="$2"
  
  echo "Checking for major version changes..." >&2
  
  # Skip major version check for branch/MR names
  if ! is_version_tag "$target_version"; then
    echo "Target is a branch/MR name ($target_version), skipping major version check" >&2
    return 0
  fi
  
  # Get current version from git
  local current_version
  current_version=$(git describe --tags --exact-match HEAD 2>/dev/null || git name-rev --name-only HEAD)
  
  # Skip check if current version is not a version tag
  if ! is_version_tag "$current_version"; then
    echo "Current version is not a version tag ($current_version), skipping major version check" >&2
    return 0
  fi
  
  # Extract major version from current version
  local current_major_version
  if [[ "$current_version" =~ ^v([0-9]+)\. ]]; then
    current_major_version="${BASH_REMATCH[1]}"
  else
    echo "Warning: Could not detect current major version from '$current_version'" >&2
    return 0  # Continue if we can't detect current version
  fi
  
  # Extract major version from target version
  local target_major_version
  if [[ "$target_version" =~ ^v([0-9]+)\. ]]; then
    target_major_version="${BASH_REMATCH[1]}"
  else
    echo "Warning: Could not detect target major version from '$target_version'" >&2
    return 0  # Continue if we can't detect target version
  fi
  
  echo "Current major version: $current_major_version" >&2
  echo "Target major version: $target_major_version" >&2
  
  # Check if major version changed
  if [ "$current_major_version" != "$target_major_version" ]; then
    if [ "$force_major" = "true" ]; then
      echo "WARNING: Major version change detected ($current_major_version -> $target_major_version)" >&2
      echo "         Forced upgrade enabled - proceeding despite major version change" >&2
      echo "         Please review BREAKING CHANGES at https://gitlab.com/isard/isardvdi/-/releases" >&2
      return 0
    else
      echo "ERROR: Major version change detected ($current_major_version -> $target_major_version)" >&2
      echo "       This may include BREAKING CHANGES that require manual intervention." >&2
      echo "       Please review the release notes at: https://gitlab.com/isard/isardvdi/-/releases" >&2
      echo "" >&2
      echo "       To force the upgrade despite breaking changes, use:" >&2
      echo "       $0 $ACTION $target_version $CONFIG_FILE --force-major-upgrade" >&2
      return 1
    fi
  else
    echo "No major version change detected - proceeding with upgrade" >&2
    return 0
  fi
}

# Function to generate cron job configuration
generate_cron_config() {
  local script_path="$(realpath "$0")"
  local config_desc="$1"
  local force_major_flag=""
  
  if [ "$FORCE_MAJOR_UPGRADE" = "true" ]; then
    force_major_flag=" --force-major-upgrade"
  fi
  
  echo "=============================================="
  echo "IsardVDI Automatic Update Cron Configuration"
  echo "=============================================="
  echo ""
  echo "📅 Schedule: Every Sunday at 04:00 AM"
  echo "🔧 Action: Automatic upgrade to latest version"
  echo "📝 Configuration: $config_desc"
  echo "📍 Script Location: $script_path"
  echo ""
  echo "⚠️  IMPORTANT NOTES:"
  echo "   - This will perform automatic upgrades including service restarts"
  echo "   - Database backups are created automatically before upgrades"
  echo "   - Logs are saved to /opt/isard-local/upgrade-logs/"
  echo "   - Major version upgrades are $([ "$FORCE_MAJOR_UPGRADE" = "true" ] && echo "ENABLED" || echo "BLOCKED")"
  echo "   - By default, ALL .cfg files in /opt/isard/src will be processed"
  echo "   - Test this configuration in a development environment first"
  echo ""
  echo "🔧 Cron Job Configuration:"
  echo "=============================================="
  echo ""
  echo "# Add this line to root's crontab (run: crontab -e as root)"
  echo "# IsardVDI automatic weekly upgrade - Sundays at 04:00 AM (all configs)"
  echo "0 4 * * 0 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "# Alternative: Daily check but only upgrade on Sundays (more conservative)"
  echo "# 0 4 * * 0 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo "# 0 4 * * 1-6 $script_path show-changes >> /var/log/isardvdi-version-check.log 2>&1"
  echo ""
  echo "🔍 Manual Installation Steps:"
  echo "=============================================="
  echo ""
  echo "1. Copy this cron job line:"
  echo "   0 4 * * 0 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "2. Edit root's crontab:"
  echo "   sudo crontab -e"
  echo ""
  echo "3. Paste the cron job line and save"
  echo ""
  echo "4. Verify the cron job is installed:"
  echo "   sudo crontab -l | grep isardvdi"
  echo ""
  echo "5. Monitor the logs:"
  echo "   tail -f /var/log/isardvdi-auto-upgrade.log"
  echo "   tail -f /opt/isard-local/upgrade-logs/\$(date +'%Y%m%d')*.md"
  echo ""
  echo "📋 Alternative Schedules:"
  echo "=============================================="
  echo ""
  echo "# Every day at 04:00 AM (all configs)"
  echo "# 0 4 * * * $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "# Every Saturday at 02:00 AM (all configs)"
  echo "# 0 2 * * 6 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "# First Sunday of every month at 03:00 AM (all configs)"
  echo "# 0 3 1-7 * 0 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "# Only pull images (no service restart) - Every day at 02:00 AM (all configs)"
  echo "# 0 2 * * * $script_path pull$force_major_flag >> /var/log/isardvdi-auto-pull.log 2>&1"
  echo ""
  echo "# Single config mode examples:"
  echo "# 0 4 * * 0 $script_path upgrade \"\" isardvdi.production.cfg$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo "# 0 4 * * 0 $script_path upgrade \"\" isardvdi.staging.cfg$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "⚙️  Advanced Configuration:"
  echo "=============================================="
  echo ""
  echo "For production environments, consider this enhanced cron setup:"
  echo ""
  echo "# Check for updates daily and log them (all configs)"
  echo "0 2 * * * $script_path show-changes >> /var/log/isardvdi-version-check.log 2>&1"
  echo ""
  echo "# Pull images daily (faster upgrades when needed, all configs)"
  echo "0 3 * * * $script_path pull >> /var/log/isardvdi-auto-pull.log 2>&1"
  echo ""
  echo "# Full upgrade only on Sundays (all configs)"
  echo "0 4 * * 0 $script_path upgrade$force_major_flag >> /var/log/isardvdi-auto-upgrade.log 2>&1"
  echo ""
  echo "# Cleanup old logs monthly"
  echo "0 5 1 * * find /opt/isard-local/upgrade-logs/ -name '*.md' -mtime +30 -delete"
  echo ""
  echo "💡 Pro Tips:"
  echo "=============================================="
  echo ""
  echo "• Test the upgrade script manually first:"
  echo "  $script_path upgrade"
  echo ""
  echo "• Preview changes before automating:"
  echo "  $script_path show-changes"
  echo ""
  echo "• Process specific configuration only:"
  echo "  $script_path upgrade \"\" isardvdi.production.cfg"
  echo ""
  echo "• Monitor disk space for Docker images and logs"
  echo "• Set up log rotation for /var/log/isardvdi-*.log files"
  echo "• Consider maintenance windows for production systems"
  echo "• Use --force-major-upgrade with caution in automated setups"
  echo ""
  if [ "$FORCE_MAJOR_UPGRADE" = "true" ]; then
    echo "⚠️  WARNING: Major version upgrades are ENABLED in this configuration!"
    echo "   This means the system will automatically upgrade across major versions"
    echo "   which may include breaking changes. Consider disabling this for production."
    echo ""
  fi
}

# Function to detect if target is a version tag or branch/MR name
is_version_tag() {
  local target="$1"
  
  # Check if it starts with 'v' followed by a number
  if [[ "$target" =~ ^v[0-9]+(\.[0-9]+)*([a-zA-Z0-9\-]*)?$ ]]; then
    return 0  # It's a version tag
  else
    return 1  # It's a branch/MR name
  fi
}

# Function to convert version tag to docker image tag format (dots to dashes)
version_to_docker_tag() {
  local version="$1"
  
  # Only convert if it's a version tag
  if is_version_tag "$version"; then
    echo "${version//./-}"   # Convert v14.74.4 to v14-74-4
  else
    echo "$version"          # Keep branch/MR names as-is
  fi
}

# Function to normalize version format (convert dashed to dotted)
normalize_version() {
  local version="$1"
  
  # Skip if empty or unknown
  if [ -z "$version" ] || [ "$version" = "unknown" ]; then
    echo "$version"
    return
  fi
  
  # Convert dashed format (v14-74-6) to dotted format (v14.74.6)
  if [[ "$version" =~ ^v[0-9]+-[0-9]+ ]]; then
    version="${version//-/.}"
  fi
  
  echo "$version"
}

# Function to compare semantic versions (returns 0 if equal, 1 if first > second, 2 if first < second)
compare_versions() {
  local version1="$1"
  local version2="$2"
  
  # If either version is not a version tag, skip comparison
  if ! is_version_tag "$version1" || ! is_version_tag "$version2"; then
    echo "Debug: Skipping version comparison - one or both targets are not version tags" >&2
    return 0  # Assume they're equal for branch/MR comparison
  fi
  
  # Normalize both versions
  version1=$(normalize_version "$version1")
  version2=$(normalize_version "$version2")
  
  # Remove 'v' prefix if present
  version1="${version1#v}"
  version2="${version2#v}"
  
  # Split versions into arrays
  IFS='.' read -ra V1 <<< "$version1"
  IFS='.' read -ra V2 <<< "$version2"
  
  # Get the maximum length of both arrays
  local max_parts=${#V1[@]}
  if [ ${#V2[@]} -gt $max_parts ]; then
    max_parts=${#V2[@]}
  fi
  
  # Compare each part (support variable-length versions)
  for (( i=0; i<max_parts; i++ )); do
    local v1_part="${V1[$i]:-0}"
    local v2_part="${V2[$i]:-0}"
    
    # Handle non-numeric parts (like alpha, beta, rc)
    if [[ "$v1_part" =~ ^[0-9]+$ ]] && [[ "$v2_part" =~ ^[0-9]+$ ]]; then
      if (( v1_part > v2_part )); then
        return 1  # version1 > version2
      elif (( v1_part < v2_part )); then
        return 2  # version1 < version2
      fi
    else
      # String comparison for non-numeric parts
      if [[ "$v1_part" > "$v2_part" ]]; then
        return 1
      elif [[ "$v1_part" < "$v2_part" ]]; then
        return 2
      fi
    fi
  done
  
  return 0  # versions are equal
}

# Function to check if target version is newer than current version
check_version_downgrade() {
  local current_version="$1"
  local target_version="$2"
  local force_major="$3"
  
  echo "Checking for version downgrade..." >&2
  echo "Debug: Current version (raw): $current_version" >&2
  echo "Debug: Target version (raw): $target_version" >&2
  
  # Skip downgrade check for branch/MR names
  if ! is_version_tag "$target_version"; then
    echo "Target is a branch/MR name ($target_version), skipping downgrade check" >&2
    return 0
  fi
  
  # Skip check if we can't determine current version or it's not a version tag
  if [ "$current_version" = "unknown" ] || [ -z "$current_version" ] || ! is_version_tag "$current_version"; then
    echo "Current version is unknown or not a version tag ($current_version), skipping downgrade check" >&2
    return 0
  fi
  
  # Normalize both versions for comparison
  local norm_current=$(normalize_version "$current_version")
  local norm_target=$(normalize_version "$target_version")
  
  echo "Debug: Current version (normalized): $norm_current" >&2
  echo "Debug: Target version (normalized): $norm_target" >&2
  
  # Compare versions
  compare_versions "$norm_current" "$norm_target"
  local comparison=$?
  
  case $comparison in
    0)
      echo "Target version is the same as current version ($norm_current)" >&2
      echo "No upgrade needed, but proceeding with requested action" >&2
      return 0
      ;;
    1)
      echo "ERROR: Downgrade detected!" >&2
      echo "       Current version: $norm_current" >&2
      echo "       Target version:  $norm_target" >&2
      echo "       Downgrades are not allowed as they may cause data loss or system instability." >&2
      echo "" >&2
      echo "       If you really need to downgrade, please:" >&2
      echo "       1. Create a full backup of your system and data" >&2
      echo "       2. Review the release notes for potential breaking changes" >&2
      echo "       3. Manually checkout the desired version using git" >&2
      echo "       4. Run the upgrade script with the --force-major-upgrade flag if needed" >&2
      return 1
      ;;
    2)
      echo "Target version is newer than current version ($norm_current -> $norm_target)" >&2
      return 0
      ;;
  esac
}

# Function to show git changes between versions
show_version_changes() {
  local current_version="$1"
  local target_version="$2"
  
  echo "=============================================="
  echo "IsardVDI Version Changes Analysis"
  echo "=============================================="
  echo ""
  echo "Current Version: $current_version"
  echo "Target:          $target_version"
  
  # Determine if target is a version tag or branch/MR
  if is_version_tag "$target_version"; then
    echo "Target Type:     Version Tag"
  else
    echo "Target Type:     Branch/MR Name"
  fi
  echo ""
  
  # Check if versions are the same
  if [ "$current_version" = "$target_version" ]; then
    echo "✅ Already on target - no changes needed"
    return 0
  fi
  
  # Check for major version changes (only if both are version tags)
  if is_version_tag "$current_version" && is_version_tag "$target_version"; then
    local current_major=""
    local target_major=""
    
    if [[ "$current_version" =~ ^v([0-9]+)\. ]]; then
      current_major="${BASH_REMATCH[1]}"
    fi
    
    if [[ "$target_version" =~ ^v([0-9]+)\. ]]; then
      target_major="${BASH_REMATCH[1]}"
    fi
    
    if [ -n "$current_major" ] && [ -n "$target_major" ] && [ "$current_major" != "$target_major" ]; then
      echo "⚠️  WARNING: MAJOR VERSION CHANGE DETECTED ($current_major -> $target_major)"
      echo "   This upgrade may include BREAKING CHANGES!"
      echo "   Please review: https://gitlab.com/isard/isardvdi/-/releases"
      echo ""
    fi
  elif ! is_version_tag "$target_version"; then
    echo "ℹ️  NOTE: Switching to branch/MR - version comparison not applicable"
    echo "   Please ensure the branch/MR is compatible with your current setup"
    echo ""
  fi
  
  # Show commit log
  echo "📋 Commit Changes:"
  echo "-------------------------------------------"
  local git_commits
  git_commits=$(git log --oneline "$current_version..$target_version" 2>/dev/null)
  
  if [ -n "$git_commits" ]; then
    echo "$git_commits"
  else
    echo "Could not retrieve git commit information between versions"
    echo "This may be normal for branch/MR targets or if references don't exist"
  fi
  
  echo ""
  echo "📊 Summary Statistics:"
  echo "-------------------------------------------"
  local commit_count
  commit_count=$(git rev-list --count "$current_version..$target_version" 2>/dev/null || echo "unknown")
  echo "Total commits: $commit_count"
  
  # Show file changes summary
  local files_changed
  files_changed=$(git diff --name-only "$current_version..$target_version" 2>/dev/null | wc -l)
  echo "Files changed: $files_changed"
  
  # Show most changed file types
  echo ""
  echo "🔧 File Types Changed:"
  echo "-------------------------------------------"
  git diff --name-only "$current_version..$target_version" 2>/dev/null | \
    sed 's/.*\.//' | sort | uniq -c | sort -nr | head -10 | \
    awk '{printf "  %-10s: %d files\n", $2, $1}' || echo "Could not analyze file changes"
  
  echo ""
  echo "📝 To see detailed changes run:"
  echo "   git log $current_version..$target_version"
  echo "   git diff $current_version..$target_version"
  echo ""
}

# Function to show usage
show_usage() {
  echo "Usage: $0 <action> [version_tag|branch_name] [config_file|--all-configs] [--force-major-upgrade] [--skip-backup-prompt]"
  echo "  action: Required action to perform - 'pull', 'upgrade', 'show-changes', or 'cron'"
  echo "    - pull: Only pull images, don't start services"
  echo "    - upgrade: Full upgrade including starting services"
  echo "    - show-changes: Show git changes from current version to target version/branch"
  echo "    - cron: Generate sample cron job configuration for automatic updates"
  echo "  version_tag|branch_name: Version tag (vX.Y.Z) or branch/MR name to upgrade to"
  echo "                          (optional, defaults to latest from GitLab for versions)"
  echo "  config_file: Configuration file to update (optional, defaults to ALL .cfg files in /opt/isard/src)"
  echo "  --all-configs: Explicitly process all .cfg files found (this is now the default behavior)"
  echo "  --force-major-upgrade: Force upgrade even if there are major version changes"
  echo "                        (bypasses breaking changes check for version tags)"
  echo "  --skip-backup-prompt: Skip interactive backup failure prompt (for automation)"
  echo ""
  echo "⚠️  IMPORTANT: Downgrades to previous versions are not allowed to prevent system instability."
  echo ""
  echo "Target Types:"
  echo "  - Version tags: v14.79.4, v15.0.0, etc. (converted to v14-79-4 for Docker)"
  echo "  - Branch names: main, develop, feature/new-api, etc. (used as-is for Docker)"
  echo "  - MR names: mr-123, fix-bug-456, etc. (used as-is for Docker)"
  echo ""
  echo "Config Processing:"
  echo "  - By default: Updates ALL .cfg files found in /opt/isard/src and builds corresponding docker-compose files"
  echo "  - Single config: Specify a single .cfg file to process only that configuration"
  echo "  - Config file naming: isardvdi.xxxxx.cfg -> uses docker-compose.xxxxx.yml"
  echo "  - Main config: isardvdi.cfg -> uses docker-compose.yml"
  echo ""
  echo "Examples:"
  echo "  $0 upgrade                                       # Full upgrade with latest version - ALL configs"
  echo "  $0 pull v14.74.4                                # Pull images for specific version - ALL configs"
  echo "  $0 upgrade main                                  # Upgrade to main branch - ALL configs"
  echo "  $0 pull feature/new-api isardvdi.staging.cfg     # Pull images for feature branch - SINGLE config"
  echo "  $0 upgrade v14.74.4 isardvdi.production.cfg     # Full upgrade with specific version - SINGLE config"
  echo "  $0 pull \"\" --all-configs                        # Pull images with latest version - ALL configs (explicit)"
  echo "  $0 upgrade v15.0.0 --force-major-upgrade        # Force upgrade to major version - ALL configs"
  echo "  $0 upgrade develop --skip-backup-prompt          # Automated upgrade to develop branch - ALL configs"
  echo "  $0 show-changes                                  # Show changes from current version to latest"
  echo "  $0 show-changes v14.75.0                        # Show changes from current version to v14.75.0"
  echo "  $0 show-changes feature/api-v2                   # Show changes from current version to feature branch"
  echo "  $0 cron                                          # Generate sample cron job for weekly updates"
}

# Parse arguments
if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ $# -lt 1 ]; then
  show_usage
  exit 0
fi

# First argument is required action
ACTION="$1"
if [ "$ACTION" != "pull" ] && [ "$ACTION" != "upgrade" ] && [ "$ACTION" != "show-changes" ] && [ "$ACTION" != "cron" ]; then
  echo "Error: First argument must be 'pull', 'upgrade', 'show-changes', or 'cron'"
  show_usage
  exit 1
fi

# Set defaults
CONFIG_FILE=""
TAG_VERSION=""
FORCE_MAJOR_UPGRADE="false"
SKIP_BACKUP_PROMPT="false"
PROCESS_ALL_CONFIGS="true"  # New default: process all configs

# Parse remaining arguments
shift  # Remove the action argument
while [ $# -gt 0 ]; do
  case "$1" in
    --force-major-upgrade)
      FORCE_MAJOR_UPGRADE="true"
      shift
      ;;
    --skip-backup-prompt)
      SKIP_BACKUP_PROMPT="true"
      shift
      ;;
    --all-configs)
      PROCESS_ALL_CONFIGS="true"
      CONFIG_FILE=""
      shift
      ;;
    *)
      # Handle positional arguments
      if [ -z "$TAG_VERSION" ]; then
        TAG_VERSION="$1"
      elif [ -z "$CONFIG_FILE" ] && [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
        # If we get a config file argument, switch to single config mode
        CONFIG_FILE="$1"
        PROCESS_ALL_CONFIGS="false"
      else
        echo "Error: Too many arguments or unknown option: $1"
        show_usage
        exit 1
      fi
      shift
      ;;
  esac
done

# Determine config files to process (will be re-evaluated after navigating to correct directory)
if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
  echo "Will process ALL configuration files found in the source directory"
else
  # Single config file mode
  if [ -z "$CONFIG_FILE" ]; then
    CONFIG_FILE="isardvdi.cfg"
  fi
  echo "Will process single configuration file: $CONFIG_FILE"
fi
echo ""

# Get version if not provided
if [ -z "$TAG_VERSION" ]; then
  TAG_VERSION=$(get_latest_version)
  echo "Using latest version: $TAG_VERSION"
fi

# Validate TAG_VERSION format and set DOCKER_IMAGE_TAG
if is_version_tag "$TAG_VERSION"; then
  echo "Target is a version tag: $TAG_VERSION"
  # Validate version tag format
  if [[ ! "$TAG_VERSION" =~ ^v[0-9]+(\.[0-9]+)*([a-zA-Z0-9\-]*)?$ ]]; then
    echo "Error: Invalid version tag format: $TAG_VERSION"
    echo "Expected format: vX.Y.Z or vX.Y.Z-suffix"
    exit 1
  fi
  TAG_DASHED=$(version_to_docker_tag "$TAG_VERSION")   # Convert to v14-74-4
else
  echo "Target is a branch/MR name: $TAG_VERSION"
  # For branch/MR names, validate they are reasonable git references
  if [[ "$TAG_VERSION" =~ [[:space:]] ]] || [[ "$TAG_VERSION" =~ [\;\&\|\$\`] ]]; then
    echo "Error: Invalid characters in branch/MR name: $TAG_VERSION"
    echo "Branch/MR names should not contain spaces or shell special characters"
    exit 1
  fi
  TAG_DASHED="$TAG_VERSION"   # Keep branch/MR names as-is for DOCKER_IMAGE_TAG
fi

echo "Git reference: $TAG_VERSION"
echo "Docker image tag: $TAG_DASHED"

# Navigate to the source directory
# Check if we're in a development environment or production
if [ -d "/opt/isard/src" ]; then
  cd /opt/isard/src || { echo "Directory /opt/isard/src not found"; exit 1; }
elif [ -f "isardvdi.cfg" ] || [ -f "docker-compose.yml" ]; then
  echo "Development environment detected - using current directory: $(pwd)"
elif [ -f "../isardvdi.cfg" ] || [ -f "../docker-compose.yml" ]; then
  echo "Running from subdirectory - moving to parent: $(dirname "$(pwd)")"
  cd .. || { echo "Could not navigate to parent directory"; exit 1; }
else
  echo "Error: Neither /opt/isard/src found nor IsardVDI files in current or parent directory"
  echo "Please run this script from the IsardVDI source directory or ensure /opt/isard/src exists"
  exit 1
fi

# Re-evaluate config files now that we're in the correct directory
if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
  # Find all .cfg files in the current directory (now should be the correct one)
  CONFIG_FILES=$(find . -maxdepth 1 -name "*.cfg" -type f 2>/dev/null | sort)
  if [ -z "$CONFIG_FILES" ]; then
    echo "No .cfg files found in current directory $(pwd) for processing"
    exit 1
  fi
  echo "Processing ALL configuration files found in $(pwd):"
  for cfg in $CONFIG_FILES; do
    echo "  - $(basename "$cfg")"
  done
  echo ""
else
  # Single config file mode - also re-validate
  if [ -z "$CONFIG_FILE" ]; then
    CONFIG_FILE="isardvdi.cfg"
  fi
  CONFIG_FILES="$CONFIG_FILE"
  echo "Processing single configuration file: $CONFIG_FILE in $(pwd)"
  echo ""
fi

# Re-validate that all config files exist and determine their compose files in the correct directory
COMPOSE_FILES=""
for cfg_file in $CONFIG_FILES; do
  cfg_file=$(basename "$cfg_file")  # Remove any ./ prefix
  
  if [ ! -f "$cfg_file" ]; then
    echo "Error: Configuration file '$cfg_file' not found in $(pwd)"
    exit 1
  fi
  
  # Determine docker-compose file based on config file
  if [ "$cfg_file" = "isardvdi.cfg" ]; then
    compose_file="docker-compose.yml"
  else
    # Extract the xxxxx part from isardvdi.xxxxx.cfg
    if [[ "$cfg_file" =~ ^isardvdi\.(.+)\.cfg$ ]]; then
      COMPOSE_SUFFIX="${BASH_REMATCH[1]}"
      compose_file="docker-compose.${COMPOSE_SUFFIX}.yml"
    else
      echo "Error: Config file must be in format 'isardvdi.xxxxx.cfg' or 'isardvdi.cfg'"
      echo "Found: $cfg_file"
      exit 1
    fi
  fi
  
  # Check if compose file exists
  if [ ! -f "$compose_file" ]; then
    echo "Error: Docker compose file '$compose_file' not found in $(pwd)"
    echo "Required for config file: $cfg_file"
    exit 1
  fi
  
  COMPOSE_FILES="$COMPOSE_FILES $compose_file"
done

echo "Configuration files to process in $(pwd):"
for cfg_file in $CONFIG_FILES; do
  cfg_file=$(basename "$cfg_file")
  if [ "$cfg_file" = "isardvdi.cfg" ]; then
    echo "  - $cfg_file -> docker-compose.yml"
  else
    suffix=$(echo "$cfg_file" | sed 's/^isardvdi\.\(.*\)\.cfg$/\1/')
    echo "  - $cfg_file -> docker-compose.${suffix}.yml"
  fi
done
echo ""

# Check and upgrade /opt/isard-pull-src/ first if it exists
PULL_SRC_DIR="/opt/isard-pull-src"
if [ -d "$PULL_SRC_DIR" ]; then
  echo "Found $PULL_SRC_DIR directory, checking for configs..."
  
  # Check if there are any .cfg files in the pull-src directory
  CFG_FILES=$(find "$PULL_SRC_DIR" -name "*.cfg" 2>/dev/null)
  
  if [ -n "$CFG_FILES" ]; then
    echo "Found configuration files in $PULL_SRC_DIR, upgrading pull-src first..."
    
    # Save current directory
    CURRENT_DIR=$(pwd)
    
    # Navigate to pull-src directory
    cd "$PULL_SRC_DIR" || { echo "Could not navigate to $PULL_SRC_DIR"; exit 1; }
    
    # Git operations for pull-src
    echo "Fetching latest changes in pull-src repository..."
    git fetch
    echo "Checking out version $TAG_VERSION in pull-src..."
    git checkout "$TAG_VERSION" || { 
      echo "Warning: Could not checkout version $TAG_VERSION in pull-src, continuing..."
    }
    
    # Update all .cfg files in pull-src
    echo "Updating DOCKER_IMAGE_TAG in all .cfg files in pull-src..."
    for cfg_file in *.cfg; do
      if [ -f "$cfg_file" ]; then
        echo "  Updating $cfg_file..."
        sed -i "s/^DOCKER_IMAGE_TAG=.*/DOCKER_IMAGE_TAG=\"$TAG_DASHED\"/" "$cfg_file"
      fi
    done
    
    # Build in pull-src if build.sh exists
    if [ -f "build.sh" ]; then
      echo "Building in pull-src directory..."
      bash build.sh || { 
        echo "Warning: Build failed in pull-src, continuing with main upgrade..."
      }
    else
      echo "No build.sh found in pull-src, skipping build step."
    fi
    
    # Pull docker images in pull-src
    echo "Pulling docker images in pull-src..."
    docker compose pull || {
      echo "Warning: Docker compose pull failed in pull-src, continuing..."
    }
    
    echo "Pull-src upgrade completed."
    
    # Return to original directory
    cd "$CURRENT_DIR" || { echo "Could not return to $CURRENT_DIR"; exit 1; }
  else
    echo "No .cfg files found in $PULL_SRC_DIR, skipping pull-src upgrade."
  fi
else
  echo "$PULL_SRC_DIR directory not found, skipping pull-src upgrade."
fi

# Handle show-changes action
if [ "$ACTION" = "show-changes" ]; then
  echo "Show changes mode - analyzing differences..."
  
  # Get current version (try first config file found, then git)
  CURRENT_VERSION=""
  FIRST_CONFIG=$(echo $CONFIG_FILES | awk '{print $1}')
  if [ -f "$FIRST_CONFIG" ]; then
    CURRENT_VERSION=$(grep "^DOCKER_IMAGE_TAG=" "$FIRST_CONFIG" 2>/dev/null | cut -d'=' -f2 | tr -d '"' || echo "")
    # Normalize version format (convert dashed to dotted)
    CURRENT_VERSION=$(normalize_version "$CURRENT_VERSION")
  fi
  if [ -z "$CURRENT_VERSION" ]; then
    CURRENT_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null || git describe --tags HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    CURRENT_VERSION=$(normalize_version "$CURRENT_VERSION")
  fi
  
  # Fetch latest changes to ensure we have up-to-date information
  echo "Fetching latest repository information..."
  git fetch
  
  # Check for downgrade in show-changes mode (just warn, don't exit)
  if is_version_tag "$CURRENT_VERSION" && is_version_tag "$TAG_VERSION"; then
    compare_versions "$CURRENT_VERSION" "$TAG_VERSION"
    version_comparison=$?
    if [ "$version_comparison" = "1" ] && [ "$CURRENT_VERSION" != "unknown" ]; then
      echo ""
      echo "⚠️  WARNING: This would be a DOWNGRADE!"
      echo "   Current version: $CURRENT_VERSION"
      echo "   Target version:  $TAG_VERSION"
      echo "   Downgrades are not recommended and are blocked by the upgrade script."
      echo ""
    fi
  fi
  
  # Show the changes
  show_version_changes "$CURRENT_VERSION" "$TAG_VERSION"
  
  # Exit after showing changes
  exit 0
fi

# Handle cron action
if [ "$ACTION" = "cron" ]; then
  echo "Cron configuration mode - generating automatic update setup..."
  
  # Use first config file for cron generation, or indicate all configs
  CRON_CONFIG_DESC=""
  if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
    CRON_CONFIG_DESC="all configurations"
  else
    CRON_CONFIG_DESC="$CONFIG_FILE"
  fi
  
  # Generate the cron configuration
  generate_cron_config "$CRON_CONFIG_DESC"
  
  # Exit after showing cron configuration
  exit 0
fi

echo "Proceeding with main IsardVDI $ACTION..."

# Acquire script lock to prevent concurrent executions
acquire_lock

# Check if there are any .cfg files in the main directory
MAIN_CFG_FILES=$(find . -maxdepth 1 -name "*.cfg" 2>/dev/null)

if [ -z "$MAIN_CFG_FILES" ]; then
  echo "No .cfg files found in $(pwd), skipping main directory processing."
  echo "Operation completed - only pull-src was processed."
  exit 0
fi

echo "Found .cfg files in main directory, proceeding with $ACTION..."

# Get current version before upgrade (use first config file)
CURRENT_VERSION=""
FIRST_CONFIG=$(echo $CONFIG_FILES | awk '{print $1}')
if [ -f "$FIRST_CONFIG" ]; then
  CURRENT_VERSION=$(grep "^DOCKER_IMAGE_TAG=" "$FIRST_CONFIG" 2>/dev/null | cut -d'=' -f2 | tr -d '"' || echo "unknown")
  # Normalize version format (convert dashed to dotted)
  CURRENT_VERSION=$(normalize_version "$CURRENT_VERSION")
fi
if [ -z "$CURRENT_VERSION" ] || [ "$CURRENT_VERSION" = "unknown" ]; then
  CURRENT_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null || git describe --tags HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  CURRENT_VERSION=$(normalize_version "$CURRENT_VERSION")
fi

# Create upgrade logs directory
UPGRADE_LOGS_DIR="/opt/isard-local/upgrade-logs"
mkdir -p "$UPGRADE_LOGS_DIR"

# Generate report filename with current datetime
REPORT_FILE="$UPGRADE_LOGS_DIR/$(date +'%Y%m%d_%H%M%S').md"

echo "Creating upgrade report: $REPORT_FILE"

# Validate all config and compose files exist
for cfg_file in $CONFIG_FILES; do
  cfg_file=$(basename "$cfg_file")
  if [ ! -f "$cfg_file" ]; then
    echo "Error: Configuration file '$cfg_file' not found in $(pwd)"
    exit 1
  fi
done

for compose_file in $COMPOSE_FILES; do
  if [ ! -f "$compose_file" ]; then
    echo "Error: Docker compose file '$compose_file' not found in $(pwd)"
    exit 1
  fi
done

if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
  echo "Processing $(echo $CONFIG_FILES | wc -w) configuration files:"
  for cfg_file in $CONFIG_FILES; do
    echo "  - $(basename "$cfg_file")"
  done
else
  echo "Using configuration file: $CONFIG_FILE"
  echo "Using docker-compose file: $COMPOSE_FILE"
fi
echo "Action: $ACTION"
echo "Target version: $TAG_VERSION"

# Database backup before upgrade (only for upgrade action)
BACKUP_INFO="No backup created"
if [ "$ACTION" = "upgrade" ]; then
  echo "Checking if database backup is needed..."
  if docker ps --format "table {{.Names}}" | grep -q "^isard-db$"; then
    echo "isard-db container is running. Creating database backup..."
    BACKUP_TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
    BACKUP_FILENAME="rethinkdb_dump_${BACKUP_TIMESTAMP}.tar.gz"
    
    docker exec -ti isard-db sh -c "mkdir -p /data/backups;cd /data/backups/; rethinkdb-dump; ls -lh" || {
      echo "Warning: Database backup failed."
      if [ "$SKIP_BACKUP_PROMPT" = "true" ]; then
        echo "Skipping backup prompt (automated mode) - continuing with upgrade..."
        BACKUP_INFO="Backup failed - continued automatically"
      else
        echo "Do you want to continue? (y/N)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
          echo "Upgrade cancelled by user."
          exit 1
        fi
        BACKUP_INFO="Backup failed - user chose to continue"
      fi
    }
    
    if [ "$BACKUP_INFO" != "Backup failed - continued automatically" ] && [ "$BACKUP_INFO" != "Backup failed - user chose to continue" ]; then
      # Get the actual backup filename from the container
      ACTUAL_BACKUP=$(docker exec isard-db sh -c "cd /data/backups && ls -t *.tar.gz 2>/dev/null | head -1" || echo "")
      if [ -n "$ACTUAL_BACKUP" ]; then
        BACKUP_INFO="Backup created: $ACTUAL_BACKUP"
      else
        BACKUP_INFO="Backup created (filename not detected)"
      fi
      echo "Database backup completed."
    fi
  else
    echo "isard-db container is not running. Skipping database backup."
    BACKUP_INFO="Container not running - backup skipped"
  fi
else
  echo "Pull action selected - skipping database backup."
  BACKUP_INFO="Skipped (pull action)"
fi

# Git operations
echo "Fetching latest changes from repository..."
git fetch

# Check for major version changes before proceeding with checkout
if ! check_major_version_change "$TAG_VERSION" "$FORCE_MAJOR_UPGRADE"; then
  update_report_error "Major version change detected - upgrade aborted (use --force-major-upgrade to override)"
  echo "Upgrade aborted due to major version change."
  exit 1
fi

# Check for version downgrade (unless it's a show-changes action)
if [ "$ACTION" != "show-changes" ]; then
  if ! check_version_downgrade "$CURRENT_VERSION" "$TAG_VERSION" "$FORCE_MAJOR_UPGRADE"; then
    update_report_error "Version downgrade detected - operation aborted"
    echo "Operation aborted due to version downgrade attempt."
    exit 1
  fi
fi

echo "Checking out version $TAG_VERSION..."
git checkout "$TAG_VERSION" || { 
  update_report_error "Could not checkout version $TAG_VERSION"
  echo "Error: Could not checkout version $TAG_VERSION"
  exit 1
}

# Generate git commit information for the report
echo "Generating upgrade report..."
GIT_COMMITS=""
if [ "$CURRENT_VERSION" != "unknown" ] && [ "$CURRENT_VERSION" != "$TAG_VERSION" ]; then
  # Get commits between old and new version
  GIT_COMMITS=$(git log --oneline "$CURRENT_VERSION..$TAG_VERSION" 2>/dev/null || echo "Could not retrieve git commit information")
else
  GIT_COMMITS="No version comparison available"
fi

# Create the upgrade report
cat > "$REPORT_FILE" << EOF
# IsardVDI $ACTION Report

**Date:** $(date '+%Y-%m-%d %H:%M:%S')  
**Script:** $0  
**Action:** $ACTION  
**Arguments:** $*

## Version Information

**Old Version:** $CURRENT_VERSION  
**New Version:** $TAG_VERSION  
**Force Major Upgrade:** $([ "$FORCE_MAJOR_UPGRADE" = "true" ] && echo "YES" || echo "NO")

## Configuration

$(if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
  echo "**Processing Mode:** All configurations"
  echo "**Config Files:** $(echo $CONFIG_FILES | wc -w) files"
  echo ""
  for cfg_file in $CONFIG_FILES; do
    cfg_basename=$(basename "$cfg_file")
    if [ "$cfg_basename" = "isardvdi.cfg" ]; then
      echo "- $cfg_basename -> docker-compose.yml"
    else
      suffix=$(echo "$cfg_basename" | sed 's/^isardvdi\.\(.*\)\.cfg$/\1/')
      echo "- $cfg_basename -> docker-compose.${suffix}.yml"
    fi
  done
else
  echo "**Processing Mode:** Single configuration"
  echo "**Config File:** $CONFIG_FILE"
  if [ "$CONFIG_FILE" = "isardvdi.cfg" ]; then
    echo "**Docker Compose File:** docker-compose.yml"
  else
    suffix=$(echo "$CONFIG_FILE" | sed 's/^isardvdi\.\(.*\)\.cfg$/\1/')
    echo "**Docker Compose File:** docker-compose.${suffix}.yml"
  fi
fi)

## Pull-Src Directory

**Status:** $([ -d "$PULL_SRC_DIR" ] && echo "Found and processed" || echo "Not found - skipped")  
$([ -d "$PULL_SRC_DIR" ] && [ -n "$CFG_FILES" ] && echo "**Config Files Updated:** $(echo "$CFG_FILES" | wc -l) files" || echo "**Config Files:** None found")

## Database Backup

$BACKUP_INFO

## Git Commit Changes

\`\`\`
$GIT_COMMITS
\`\`\`

## $ACTION Status

$ACTION initiated at $(date '+%Y-%m-%d %H:%M:%S')
EOF

echo "Upgrade report initialized: $REPORT_FILE"

# Update DOCKER_IMAGE_TAG in all config files
echo "Updating DOCKER_IMAGE_TAG in configuration files..."
for cfg_file in $CONFIG_FILES; do
  cfg_basename=$(basename "$cfg_file")
  echo "  Updating $cfg_basename..."
  sed -i "s/^DOCKER_IMAGE_TAG=.*/DOCKER_IMAGE_TAG=\"$TAG_DASHED\"/" "$cfg_basename"
done

# Build and deploy
echo "Building IsardVDI..."
bash build.sh || { 
  update_report_error "Build failed"
  echo "Error: Build failed"
  exit 1
}

echo "Pulling latest docker images..."
docker compose pull

if [ "$ACTION" = "upgrade" ]; then
  echo "Starting services for all configurations..."
  
  # Process each configuration and its corresponding compose file
  for cfg_file in $CONFIG_FILES; do
    cfg_basename=$(basename "$cfg_file")
    
    # Determine compose file for this config
    if [ "$cfg_basename" = "isardvdi.cfg" ]; then
      compose_file="docker-compose.yml"
    else
      suffix=$(echo "$cfg_basename" | sed 's/^isardvdi\.\(.*\)\.cfg$/\1/')
      compose_file="docker-compose.${suffix}.yml"
    fi
    
    echo "  Starting services for $cfg_basename using $compose_file..."
    
    # Check if docker-compose-open-ports.yml exists and build compose command accordingly
    if [ -f "docker-compose-open-ports.yml" ]; then
      echo "    Found docker-compose-open-ports.yml, including it in the deployment..."
      docker compose -f "$compose_file" -f docker-compose-open-ports.yml up -d
    else
      echo "    docker-compose-open-ports.yml not found, using only $compose_file..."
      docker compose -f "$compose_file" up -d
    fi
  done
  
  echo "Upgrade completed successfully!"
  echo "IsardVDI has been upgraded to version $TAG_VERSION"
  echo "All $(echo $CONFIG_FILES | wc -w) configurations have been processed"
  
  ACTION_STATUS="SUCCESS"
  ACTION_MESSAGE="Upgrade completed successfully for all configurations!"
else
  echo "Pull completed successfully!"
  echo "Images have been pulled for version $TAG_VERSION"
  if [ "$PROCESS_ALL_CONFIGS" = "true" ]; then
    echo "All $(echo $CONFIG_FILES | wc -w) configurations have been updated"
  else
    echo "Configuration $CONFIG_FILE has been updated"
  fi
  echo "Services were not started (pull action selected)"
  
  ACTION_STATUS="SUCCESS"
  ACTION_MESSAGE="Pull completed successfully! All configurations updated, services were not started."
fi

# Update the upgrade report with completion status
cat >> "$REPORT_FILE" << EOF

## $ACTION Completion

**Status:** $ACTION_STATUS  
**Completed at:** $(date '+%Y-%m-%d %H:%M:%S')  
**Final Version:** $TAG_VERSION  

$ACTION_MESSAGE
EOF

echo "Report finalized: $REPORT_FILE"