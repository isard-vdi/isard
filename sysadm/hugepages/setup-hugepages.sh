#!/bin/bash
# setup-hugepages.sh - Detect and configure 1G hugepages for IsardVDI GPU desktops
#
# On x86_64, the maximum hugepage size is 1GB (requires CPU flag pdpe1gb).
# 2MB hugepages are always available but provide less benefit for VFIO.
#
# This script:
#   1. Checks CPU support for 1G hugepages
#   2. Shows current hugepage configuration
#   3. Optionally configures hugepages via GRUB (requires reboot)
#
# Usage:
#   ./setup-hugepages.sh              # Check current status
#   ./setup-hugepages.sh --apply N    # Configure N x 1G hugepages (needs root + reboot)
#   ./setup-hugepages.sh --apply N --size 2M  # Use 2M pages instead (fallback)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

read_sysfs() {
    local path="$1"
    if [ -f "$path" ]; then
        cat "$path" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

detect_cpu_support() {
    echo -e "\n${BOLD}=== CPU Hugepage Support ===${NC}\n"

    if grep -q pdpe1gb /proc/cpuinfo 2>/dev/null; then
        ok "CPU supports 1G hugepages (pdpe1gb flag present)"
        SUPPORTS_1G=true
    else
        warn "CPU does NOT support 1G hugepages (pdpe1gb flag missing)"
        warn "Only 2M hugepages available (less benefit for VFIO)"
        SUPPORTS_1G=false
    fi

    if grep -q pse /proc/cpuinfo 2>/dev/null; then
        ok "CPU supports 2M hugepages (pse flag present)"
    fi
}

detect_current_config() {
    echo -e "\n${BOLD}=== Current Hugepage Configuration ===${NC}\n"

    local has_any=false

    # 1G hugepages
    local dir_1g="/sys/kernel/mm/hugepages/hugepages-1048576kB"
    if [ -d "$dir_1g" ]; then
        local total_1g free_1g
        total_1g=$(read_sysfs "$dir_1g/nr_hugepages")
        free_1g=$(read_sysfs "$dir_1g/free_hugepages")
        if [ "$total_1g" -gt 0 ]; then
            ok "1G hugepages: ${total_1g} total, ${free_1g} free ($(( total_1g - free_1g )) in use)"
            has_any=true
        else
            info "1G hugepages: not allocated (0 pages)"
        fi
    else
        info "1G hugepages: not available on this kernel"
    fi

    # 2M hugepages
    local dir_2m="/sys/kernel/mm/hugepages/hugepages-2048kB"
    if [ -d "$dir_2m" ]; then
        local total_2m free_2m
        total_2m=$(read_sysfs "$dir_2m/nr_hugepages")
        free_2m=$(read_sysfs "$dir_2m/free_hugepages")
        if [ "$total_2m" -gt 0 ]; then
            ok "2M hugepages: ${total_2m} total, ${free_2m} free ($(( total_2m - free_2m )) in use)"
            has_any=true
        else
            info "2M hugepages: not allocated (0 pages)"
        fi
    fi

    # hugetlbfs mount
    echo ""
    if mountpoint -q /dev/hugepages 2>/dev/null; then
        ok "/dev/hugepages is mounted (hugetlbfs)"
    else
        warn "/dev/hugepages is NOT mounted"
    fi

    # GRUB config
    echo ""
    local grub_file="/etc/default/grub"
    if [ -f "$grub_file" ]; then
        local cmdline
        cmdline=$(grep '^GRUB_CMDLINE_LINUX=' "$grub_file" | head -1)
        if echo "$cmdline" | grep -q hugepages; then
            info "GRUB hugepage params found: $(echo "$cmdline" | grep -oP 'hugepages\S*|hugepagesz\S*|default_hugepagesz\S*' | tr '\n' ' ')"
        else
            info "No hugepage parameters in GRUB config"
        fi
    fi

    # Summary
    echo ""
    if [ "$has_any" = true ]; then
        ok "Hugepages are ACTIVE. IsardVDI will auto-detect and use them for GPU desktops."
    else
        warn "No hugepages allocated. GPU desktops will use standard 4K pages (slower VFIO startup)."
        echo ""
        echo -e "  To configure, run:  ${BOLD}sudo $0 --apply <N>${NC}"
        echo -e "  where N = number of 1G pages (each page = 1GB of RAM for GPU VMs)"
        echo ""
        echo -e "  ${BOLD}Example:${NC} 10 GPU desktops x 8GB each = 80GB needed = 80 pages"
        echo -e "           sudo $0 --apply 80"
    fi
}

detect_memory_info() {
    echo -e "\n${BOLD}=== Memory Summary ===${NC}\n"

    local total_kb
    total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_gb=$(( total_kb / 1048576 ))
    local available_kb
    available_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local available_gb=$(( available_kb / 1048576 ))

    info "Total RAM:     ${total_gb} GB"
    info "Available RAM: ${available_gb} GB"

    # Suggest leaving at least 16GB for the host OS + non-GPU VMs
    local reserve_gb=16
    local max_hugepages=$(( (total_gb - reserve_gb) > 0 ? total_gb - reserve_gb : 0 ))
    info "Suggested max 1G hugepages: ${max_hugepages} (reserves ${reserve_gb}GB for OS + non-GPU VMs)"
}

# ---------------------------------------------------------------------------
# Apply configuration
# ---------------------------------------------------------------------------

apply_hugepages() {
    local num_pages="$1"
    local page_size="${2:-1G}"

    if [ "$(id -u)" -ne 0 ]; then
        err "Must be run as root to apply changes. Use: sudo $0 --apply $num_pages"
        exit 1
    fi

    if [ "$num_pages" -lt 1 ] 2>/dev/null; then
        err "Number of pages must be a positive integer"
        exit 1
    fi

    if [ "$page_size" = "1G" ] && [ "$SUPPORTS_1G" != "true" ]; then
        err "CPU does not support 1G hugepages. Use --size 2M instead."
        exit 1
    fi

    local grub_file="/etc/default/grub"
    if [ ! -f "$grub_file" ]; then
        err "$grub_file not found. Is this an Ubuntu/Debian system with GRUB?"
        exit 1
    fi

    # Build kernel parameters
    local hugepages_params
    if [ "$page_size" = "1G" ]; then
        hugepages_params="hugepagesz=1G default_hugepagesz=1G hugepages=${num_pages}"
        info "Configuring ${num_pages} x 1G hugepages (${num_pages}GB total reserved)"
    else
        hugepages_params="hugepagesz=2M default_hugepagesz=2M hugepages=${num_pages}"
        local total_mb=$(( num_pages * 2 ))
        info "Configuring ${num_pages} x 2M hugepages (${total_mb}MB total reserved)"
    fi

    # Backup GRUB config
    local backup="${grub_file}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$grub_file" "$backup"
    ok "Backed up $grub_file to $backup"

    # Read current GRUB_CMDLINE_LINUX and strip any existing hugepage params
    local current_cmdline
    current_cmdline=$(grep '^GRUB_CMDLINE_LINUX=' "$grub_file" | head -1 | sed 's/^GRUB_CMDLINE_LINUX="//' | sed 's/"$//')
    local clean_cmdline
    clean_cmdline=$(echo "$current_cmdline" | sed -E 's/\s*(hugepagesz|default_hugepagesz|hugepages)=[^ ]*//g' | xargs)

    # Append new hugepage params
    local new_cmdline
    if [ -z "$clean_cmdline" ]; then
        new_cmdline="$hugepages_params"
    else
        new_cmdline="${clean_cmdline} ${hugepages_params}"
    fi

    # Write updated GRUB config
    sed -i "s|^GRUB_CMDLINE_LINUX=.*|GRUB_CMDLINE_LINUX=\"${new_cmdline}\"|" "$grub_file"
    ok "Updated $grub_file:"
    info "  GRUB_CMDLINE_LINUX=\"${new_cmdline}\""

    # Update GRUB
    echo ""
    info "Updating GRUB bootloader..."
    if command -v update-grub &>/dev/null; then
        update-grub
    elif command -v grub2-mkconfig &>/dev/null; then
        grub2-mkconfig -o /boot/grub2/grub.cfg
    elif command -v grub-mkconfig &>/dev/null; then
        grub-mkconfig -o /boot/grub/grub.cfg
    else
        warn "Could not find grub update command. Run 'update-grub' manually."
    fi

    echo ""
    ok "Hugepages configured successfully."
    echo ""
    echo -e "  ${BOLD}${RED}REBOOT REQUIRED${NC}${BOLD} to allocate 1G hugepages.${NC}"
    echo -e "  1G pages require contiguous physical memory and can only be"
    echo -e "  reserved at boot time."
    echo ""
    echo -e "  After reboot, verify with:"
    echo -e "    grep Huge /proc/meminfo"
    echo -e "    $0"
    echo ""
    echo -e "  IsardVDI will auto-detect the hugepages and use them for GPU desktops."
}

# ---------------------------------------------------------------------------
# Remove configuration
# ---------------------------------------------------------------------------

remove_hugepages() {
    if [ "$(id -u)" -ne 0 ]; then
        err "Must be run as root. Use: sudo $0 --remove"
        exit 1
    fi

    local grub_file="/etc/default/grub"
    if [ ! -f "$grub_file" ]; then
        err "$grub_file not found."
        exit 1
    fi

    local backup="${grub_file}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$grub_file" "$backup"
    ok "Backed up $grub_file to $backup"

    local current_cmdline
    current_cmdline=$(grep '^GRUB_CMDLINE_LINUX=' "$grub_file" | head -1 | sed 's/^GRUB_CMDLINE_LINUX="//' | sed 's/"$//')
    local clean_cmdline
    clean_cmdline=$(echo "$current_cmdline" | sed -E 's/\s*(hugepagesz|default_hugepagesz|hugepages)=[^ ]*//g' | xargs)

    sed -i "s|^GRUB_CMDLINE_LINUX=.*|GRUB_CMDLINE_LINUX=\"${clean_cmdline}\"|" "$grub_file"
    ok "Removed hugepage parameters from GRUB config"

    info "Updating GRUB bootloader..."
    if command -v update-grub &>/dev/null; then
        update-grub
    elif command -v grub2-mkconfig &>/dev/null; then
        grub2-mkconfig -o /boot/grub2/grub.cfg
    elif command -v grub-mkconfig &>/dev/null; then
        grub-mkconfig -o /boot/grub/grub.cfg
    fi

    echo ""
    ok "Hugepage configuration removed. Reboot to take effect."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SUPPORTS_1G=false

detect_cpu_support

case "${1:-}" in
    --apply)
        if [ -z "${2:-}" ]; then
            err "Usage: $0 --apply <num_pages> [--size 1G|2M]"
            exit 1
        fi
        PAGE_SIZE="1G"
        if [ "${3:-}" = "--size" ] && [ -n "${4:-}" ]; then
            PAGE_SIZE="$4"
        fi
        detect_memory_info
        echo ""
        apply_hugepages "$2" "$PAGE_SIZE"
        ;;
    --remove)
        remove_hugepages
        ;;
    --help|-h)
        echo ""
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "  (no args)         Check current hugepage status"
        echo "  --apply N         Configure N hugepages and update GRUB (needs root + reboot)"
        echo "  --apply N --size 2M  Use 2M pages instead of 1G (fallback for older CPUs)"
        echo "  --remove          Remove hugepage config from GRUB (needs root + reboot)"
        echo "  --help            Show this help"
        echo ""
        echo "On x86_64, supported hugepage sizes are:"
        echo "  1G  - requires CPU flag pdpe1gb (all modern Xeon/EPYC CPUs)"
        echo "        best for GPU desktops (reduces VFIO IOMMU mapping 262,000x)"
        echo "  2M  - always available, moderate VFIO benefit"
        echo ""
        echo "Example: reserve 80GB for GPU desktops (10 VMs x 8GB each):"
        echo "  sudo $0 --apply 80"
        echo ""
        ;;
    *)
        detect_memory_info
        detect_current_config
        ;;
esac
