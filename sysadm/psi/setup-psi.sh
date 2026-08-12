#!/bin/bash
# setup-psi.sh - Check and enable kernel Pressure Stall Information (PSI)
#
# The storage task governor reads /proc/pressure/{cpu,io,memory} to hold back
# heavy background work while a node is under load. Reading a missing PSI file
# is treated as "no pressure", so on a kernel without PSI the governor still
# enforces its concurrency cap but never reacts to load. Nothing fails and
# nothing is logged: the difference is silent, which is why this script exists.
#
# Most distributions ship PSI enabled. Some — notably Oracle Linux's UEK —
# build it in but leave it off by default (CONFIG_PSI_DEFAULT_DISABLED=y),
# in which case it is turned on with the psi=1 kernel parameter and a reboot.
#
# Usage:
#   ./setup-psi.sh            # Report status (safe, read-only)
#   ./setup-psi.sh --apply    # Add psi=1 to GRUB (needs root + reboot)
#   ./setup-psi.sh --remove   # Remove psi=1 from GRUB (needs root + reboot)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

PSI_ACTIVE=false
PSI_COMPILED=unknown
FIXABLE=false

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

# Grep the kernel config wherever it lives. Streams it rather than capturing a
# 300 KB blob into a variable. Returns non-zero when no config is readable, so
# "config missing" stays distinguishable from "option absent".
KCONFIG_SRC=""

find_kernel_config() {
    local cfg
    cfg="/boot/config-$(uname -r)"
    if [ -r "$cfg" ]; then
        KCONFIG_SRC="$cfg"
        return 0
    fi
    if [ -r /proc/config.gz ] && command -v zcat &>/dev/null; then
        KCONFIG_SRC="/proc/config.gz"
        return 0
    fi
    return 1
}

kconfig_has() {
    # kconfig_has CONFIG_FOO=y  ->  0 when present
    [ -n "$KCONFIG_SRC" ] || return 1
    if [ "$KCONFIG_SRC" = "/proc/config.gz" ]; then
        zcat "$KCONFIG_SRC" 2>/dev/null | grep -qx -- "$1"
    else
        grep -qx -- "$1" "$KCONFIG_SRC" 2>/dev/null
    fi
}

detect_runtime() {
    echo -e "\n${BOLD}=== PSI runtime state ===${NC}\n"

    if [ -d /proc/pressure ]; then
        PSI_ACTIVE=true
        ok "/proc/pressure exists — PSI is active"
        local f
        for f in cpu io memory; do
            if [ -r "/proc/pressure/$f" ]; then
                info "  $f: $(head -1 "/proc/pressure/$f")"
            else
                warn "  $f: not readable"
            fi
        done
    else
        warn "/proc/pressure does NOT exist — PSI is unavailable on this host"
        info "The governor's pressure axis is inert here: heavy background work"
        info "is still capped by max_heavy, but it will not back off under load."
    fi
}

detect_kernel_support() {
    echo -e "\n${BOLD}=== Kernel support ===${NC}\n"

    if ! find_kernel_config; then
        warn "Kernel config not readable (no /boot/config-$(uname -r), no /proc/config.gz)"
        info "Cannot tell whether PSI is compiled in; check your distribution's kernel."
        return
    fi
    info "Reading $KCONFIG_SRC"

    if kconfig_has 'CONFIG_PSI=y'; then
        PSI_COMPILED=yes
        ok "CONFIG_PSI=y — PSI is compiled into this kernel"
    else
        PSI_COMPILED=no
        warn "CONFIG_PSI is not enabled — this kernel cannot provide PSI at all"
        info "Enabling it would require a different kernel; psi=1 will not help."
        return
    fi

    if kconfig_has 'CONFIG_PSI_DEFAULT_DISABLED=y'; then
        warn "CONFIG_PSI_DEFAULT_DISABLED=y — compiled in, but OFF unless asked for"
        if grep -qw 'psi=1' /proc/cmdline; then
            info "psi=1 is present on the current command line"
        else
            info "psi=1 is NOT on the current command line ($(cat /proc/cmdline))"
            FIXABLE=true
        fi
    else
        ok "CONFIG_PSI_DEFAULT_DISABLED is not set — PSI is on by default"
    fi
}

verdict() {
    echo -e "\n${BOLD}=== Verdict ===${NC}\n"

    if [ "$PSI_ACTIVE" = true ]; then
        ok "Nothing to do — the governor can read pressure on this host."
        return 0
    fi

    if [ "$FIXABLE" = true ]; then
        warn "PSI is available but switched off. Enable it with:"
        echo ""
        echo -e "    ${BOLD}sudo $0 --apply${NC}"
        echo ""
        info "That adds psi=1 to the kernel command line. A reboot is required."
        return 0
    fi

    if [ "$PSI_COMPILED" = no ]; then
        warn "This kernel cannot provide PSI. The governor will run without its"
        warn "pressure axis; its concurrency cap still applies."
        return 0
    fi

    warn "PSI is not active and the cause is not conclusive from here."
    info "Check the kernel command line and your distribution's kernel options."
}

# ---------------------------------------------------------------------------
# Apply / remove
# ---------------------------------------------------------------------------

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        err "This needs root. Re-run with sudo."
        exit 1
    fi
}

regenerate_grub() {
    if command -v update-grub &>/dev/null; then
        update-grub
    elif command -v grub2-mkconfig &>/dev/null; then
        # Oracle Linux / RHEL: BIOS and UEFI keep grub.cfg in different places.
        if [ -d /sys/firmware/efi ] && [ -f /boot/efi/EFI/redhat/grub.cfg ]; then
            grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg
        else
            grub2-mkconfig -o /boot/grub2/grub.cfg
        fi
    elif command -v grub-mkconfig &>/dev/null; then
        grub-mkconfig -o /boot/grub/grub.cfg
    else
        warn "No grub update command found. Regenerate the GRUB config manually."
    fi
}

apply_psi() {
    require_root

    if [ "$PSI_ACTIVE" = true ]; then
        ok "PSI is already active — nothing to change."
        exit 0
    fi
    if [ "$PSI_COMPILED" = no ]; then
        err "CONFIG_PSI is not enabled in this kernel; psi=1 would have no effect."
        exit 1
    fi

    local grub_file="/etc/default/grub"
    [ -f "$grub_file" ] || { err "$grub_file not found."; exit 1; }

    if grep -E '^GRUB_CMDLINE_LINUX(_DEFAULT)?=' "$grub_file" | grep -qw 'psi=1'; then
        ok "psi=1 is already in $grub_file — reboot to apply it."
        exit 0
    fi

    local backup
    backup="${grub_file}.psi-$(date +%Y%m%d-%H%M%S)"
    cp -a "$grub_file" "$backup"
    info "Backed up $grub_file to $backup"

    # Append to GRUB_CMDLINE_LINUX, which every supported distribution defines.
    if grep -q '^GRUB_CMDLINE_LINUX=' "$grub_file"; then
        sed -i 's/^\(GRUB_CMDLINE_LINUX="[^"]*\)"/\1 psi=1"/' "$grub_file"
    else
        echo 'GRUB_CMDLINE_LINUX="psi=1"' >> "$grub_file"
    fi

    grep '^GRUB_CMDLINE_LINUX=' "$grub_file" | head -1 | sed 's/^/    /'
    regenerate_grub

    echo ""
    ok "psi=1 added to the kernel command line."
    echo ""
    echo -e "  ${BOLD}${RED}REBOOT REQUIRED${NC}${BOLD} for PSI to become available.${NC}"
    echo ""
    echo -e "  After reboot, verify with:"
    echo -e "    cat /proc/pressure/cpu"
    echo -e "    $0"
}

remove_psi() {
    require_root

    local grub_file="/etc/default/grub"
    [ -f "$grub_file" ] || { err "$grub_file not found."; exit 1; }

    if ! grep -E '^GRUB_CMDLINE_LINUX(_DEFAULT)?=' "$grub_file" | grep -qw 'psi=1'; then
        info "psi=1 is not in $grub_file — nothing to remove."
        exit 0
    fi

    local backup
    backup="${grub_file}.psi-$(date +%Y%m%d-%H%M%S)"
    cp -a "$grub_file" "$backup"
    info "Backed up $grub_file to $backup"

    sed -i 's/ *psi=1//g' "$grub_file"
    grep '^GRUB_CMDLINE_LINUX=' "$grub_file" | head -1 | sed 's/^/    /'
    regenerate_grub

    echo ""
    ok "psi=1 removed. Reboot to take effect."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

detect_runtime
detect_kernel_support

case "${1:-}" in
    --apply)  apply_psi ;;
    --remove) remove_psi ;;
    "")       verdict ;;
    *)        err "Unknown option: $1"; sed -n '15,18p' "$0"; exit 1 ;;
esac
