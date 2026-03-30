#!/bin/bash
#
# IsardVDI - Kernel sysctl optimization for video streaming (VNC/SPICE/RDP)
#
# Optimizes network stack for low-latency, high-throughput WebSocket and
# TCP tunnel traffic between HAProxy, websockify, squid, guacamole and
# QEMU hypervisors.
#
# Usage:
#   sudo bash sysctl-video-optimize.sh          # Apply and persist
#   sudo bash sysctl-video-optimize.sh --check  # Show current vs recommended values
#
# Persists to /etc/sysctl.d/99-isardvdi-video.conf
#

set -e

SYSCTL_CONF="/etc/sysctl.d/99-isardvdi-video.conf"

declare -A SETTINGS

# --- TCP latency ---
# Disable Nagle's algorithm system-wide for low-latency video frames
SETTINGS[net.ipv4.tcp_low_latency]=1

# --- Connection backlog ---
# Maximum pending connections. Handles burst of viewer connections.
SETTINGS[net.core.somaxconn]=65535
SETTINGS[net.ipv4.tcp_max_syn_backlog]=65535

# --- TCP buffer sizes ---
# min/default/max in bytes. Larger buffers for video frame bursts.
# Default kernel is 4K/87K/6M. We raise default to 256K for streaming.
SETTINGS[net.ipv4.tcp_rmem]="4096 262144 16777216"
SETTINGS[net.ipv4.tcp_wmem]="4096 262144 16777216"
SETTINGS[net.core.rmem_default]=262144
SETTINGS[net.core.wmem_default]=262144
SETTINGS[net.core.rmem_max]=16777216
SETTINGS[net.core.wmem_max]=16777216

# --- TCP keepalive ---
# Detect dead viewer sessions faster (default: 7200/75/9 = ~2.5h)
# With these: 60 + 10*6 = 120s to detect dead connection
SETTINGS[net.ipv4.tcp_keepalive_time]=60
SETTINGS[net.ipv4.tcp_keepalive_intvl]=10
SETTINGS[net.ipv4.tcp_keepalive_probes]=6

# --- TCP performance ---
# Enable TCP window scaling for high-bandwidth video streams
SETTINGS[net.ipv4.tcp_window_scaling]=1
# Enable timestamps for better RTT estimation
SETTINGS[net.ipv4.tcp_timestamps]=1
# Enable selective ACKs to recover from packet loss without retransmitting everything
SETTINGS[net.ipv4.tcp_sack]=1
# Fast retransmit on 2 duplicate ACKs (default 3) for quicker recovery
SETTINGS[net.ipv4.tcp_reordering]=2

# --- TCP congestion ---
# BBR gives better throughput and lower latency than cubic for streaming
SETTINGS[net.ipv4.tcp_congestion_control]=bbr
# Fair queueing scheduler works best with BBR
SETTINGS[net.core.default_qdisc]=fq

# --- Connection recycling ---
# Reuse TIME_WAIT sockets for new connections (2 = client+server, safe for internal Docker traffic)
SETTINGS[net.ipv4.tcp_tw_reuse]=2
# Faster FIN timeout (default 60s)
SETTINGS[net.ipv4.tcp_fin_timeout]=15

# --- Network queue ---
# Increase the max number of queued packets when interface receives faster than kernel processes
SETTINGS[net.core.netdev_max_backlog]=16384
# Increase max number of packets queued on OUTPUT
SETTINGS[net.core.optmem_max]=131072

# --- File descriptors ---
# Each viewer session = multiple FDs (WS + TCP + HAProxy). Allow plenty of headroom.
# Only set if current value is lower.
SETTINGS[fs.file-max]=2097152

check_mode() {
    echo "IsardVDI Video Sysctl - Current vs Recommended"
    echo "================================================"
    printf "%-45s %-20s %-20s %s\n" "PARAMETER" "CURRENT" "RECOMMENDED" "STATUS"
    echo "----------------------------------------------------------------------------------------------------------------"

    local changes_needed=0
    for key in $(echo "${!SETTINGS[@]}" | tr ' ' '\n' | sort); do
        recommended="${SETTINGS[$key]}"
        current=$(sysctl -n "$key" 2>/dev/null | tr '\t' ' ' || echo "N/A")

        if [ "$current" = "$recommended" ]; then
            status="OK"
        elif [ "$key" = "fs.file-max" ] || [ "$key" = "net.core.optmem_max" ]; then
            # For these, current >= recommended is fine
            if [ "$current" -ge "$recommended" ] 2>/dev/null; then
                status="OK (higher)"
            else
                status="CHANGE"
                changes_needed=$((changes_needed + 1))
            fi
        else
            status="CHANGE"
            changes_needed=$((changes_needed + 1))
        fi
        printf "%-45s %-20s %-20s %s\n" "$key" "$current" "$recommended" "$status"
    done

    echo ""
    if [ $changes_needed -eq 0 ]; then
        echo "All settings are already optimized."
    else
        echo "$changes_needed setting(s) need updating. Run without --check to apply."
    fi
}

apply_settings() {
    # Check if BBR module is available
    if ! modprobe tcp_bbr 2>/dev/null; then
        echo "WARNING: tcp_bbr module not available. Falling back to cubic."
        SETTINGS[net.ipv4.tcp_congestion_control]=cubic
        SETTINGS[net.core.default_qdisc]=fq_codel
    fi

    echo "# IsardVDI Video Streaming Optimization" > "$SYSCTL_CONF"
    echo "# Generated on $(date -Iseconds)" >> "$SYSCTL_CONF"
    echo "# Optimized for low-latency VNC/SPICE/RDP proxying" >> "$SYSCTL_CONF"
    echo "" >> "$SYSCTL_CONF"

    for key in $(echo "${!SETTINGS[@]}" | tr ' ' '\n' | sort); do
        echo "$key = ${SETTINGS[$key]}" >> "$SYSCTL_CONF"
    done

    echo ""
    echo "Applying settings..."
    sysctl -p "$SYSCTL_CONF"

    echo ""
    echo "Done. Settings written to $SYSCTL_CONF (persistent across reboots)."
    echo ""
    echo "Verify with: sudo bash $0 --check"
}

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)." >&2
    exit 1
fi

case "${1:-}" in
    --check)
        check_mode
        ;;
    *)
        apply_settings
        ;;
esac
