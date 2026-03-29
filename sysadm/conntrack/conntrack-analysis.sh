#!/bin/bash
# conntrack-analysis.sh - Comprehensive connection tracking analysis
# For IsardVDI + Docker + OVS environments
#
# Usage: ./conntrack-analysis.sh [OPTIONS]
#   -j, --json     Output in JSON format
#   -c, --color    Force color output (auto-detected for TTY)
#   -n, --no-color Disable color output
#   -h, --help     Show this help message

# ============================================================================
# Configuration and Defaults
# ============================================================================

JSON_OUTPUT=false
USE_COLOR=auto

# Color codes (will be set based on USE_COLOR)
RED=""
YELLOW=""
GREEN=""
BLUE=""
BOLD=""
RESET=""

# IsardVDI-specific port names
declare -A PORT_NAMES=(
    [22]="SSH"
    [53]="DNS"
    [80]="HTTP"
    [443]="HTTPS/WireGuard-Users"
    [4443]="WireGuard-Hypers"
    [2022]="Hyper SSH"
    [3000]="Grafana"
    [3100]="Loki"
    [3306]="MySQL"
    [3389]="RDP"
    [4443]="Websockify"
    [4567]="IsardVDI Stats"
    [4822]="Guacamole"
    [5000]="IsardVDI API"
    [5432]="PostgreSQL"
    [5900]="VNC"
    [6081]="GENEVE"
    [6379]="Redis"
    [8080]="HTTP-ALT"
    [9090]="Prometheus"
    [28015]="RethinkDB"
)

# Docker container IP mapping (populated at runtime)
declare -A DOCKER_CONTAINERS

# ============================================================================
# Argument Parsing
# ============================================================================

show_help() {
    cat << 'EOF'
conntrack-analysis.sh - Connection tracking analysis for IsardVDI

USAGE:
    ./conntrack-analysis.sh [OPTIONS]

OPTIONS:
    -j, --json      Output in JSON format (for scripting/monitoring)
    -c, --color     Force color output
    -n, --no-color  Disable color output
    -h, --help      Show this help message

EXAMPLES:
    ./conntrack-analysis.sh              # Normal output with auto-color
    ./conntrack-analysis.sh -j           # JSON output
    ./conntrack-analysis.sh -j | jq .    # Pretty-print JSON
    ./conntrack-analysis.sh -c           # Force colors (e.g., in pipe)

REQUIREMENTS:
    - conntrack-tools package (conntrack command)
    - Docker (optional, for container name resolution)
    - OVS (optional, for OVS conntrack stats)
EOF
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -j|--json)
            JSON_OUTPUT=true
            shift
            ;;
        -c|--color)
            USE_COLOR=always
            shift
            ;;
        -n|--no-color)
            USE_COLOR=never
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_help
            exit 1
            ;;
    esac
done

# ============================================================================
# Color Setup
# ============================================================================

setup_colors() {
    if [[ "$USE_COLOR" == "always" ]] || { [[ "$USE_COLOR" == "auto" ]] && [[ -t 1 ]]; }; then
        RED='\033[0;31m'
        YELLOW='\033[0;33m'
        GREEN='\033[0;32m'
        BLUE='\033[0;34m'
        BOLD='\033[1m'
        RESET='\033[0m'
    fi
}

# ============================================================================
# Docker Container Resolution
# ============================================================================

build_docker_mapping() {
    # Check if docker is available
    if ! command -v docker &>/dev/null; then
        return
    fi

    # Get all container IPs from all networks
    local networks
    networks=$(docker network ls --format '{{.Name}}' 2>/dev/null) || return

    for network in $networks; do
        local output
        output=$(docker network inspect "$network" \
            --format '{{range .Containers}}{{.IPv4Address}}|{{.Name}}{{"\n"}}{{end}}' 2>/dev/null) || continue

        while IFS='|' read -r ip name; do
            [[ -z "$ip" || -z "$name" ]] && continue
            # Remove CIDR suffix if present
            ip="${ip%%/*}"
            DOCKER_CONTAINERS["$ip"]="$name"
        done <<< "$output"
    done
}

resolve_ip() {
    local ip="$1"
    local container="${DOCKER_CONTAINERS[$ip]:-}"

    if [[ -n "$container" ]]; then
        echo "$container"
    elif [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]]; then
        echo "docker-unknown"
    elif [[ "$ip" =~ ^10\.2\. ]]; then
        echo "vlan-wg"
    elif [[ "$ip" =~ ^10\.1\. ]]; then
        echo "wg-hyper"
    elif [[ "$ip" =~ ^10\.0\. ]]; then
        echo "wg-user"
    elif [[ "$ip" =~ ^10\. ]]; then
        echo "internal"
    elif [[ "$ip" =~ ^172\. ]]; then
        echo "private"
    elif [[ "$ip" =~ ^192\.168\. ]]; then
        echo "private"
    elif [[ "$ip" =~ ^127\. ]]; then
        echo "localhost"
    else
        echo "external"
    fi
}

get_ip_type() {
    local ip="$1"
    if [[ -n "${DOCKER_CONTAINERS[$ip]:-}" ]]; then
        echo "docker"
    elif [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]]; then
        echo "docker"
    elif [[ "$ip" =~ ^10\. ]] || [[ "$ip" =~ ^172\. ]] || [[ "$ip" =~ ^192\.168\. ]]; then
        echo "internal"
    elif [[ "$ip" =~ ^127\. ]]; then
        echo "localhost"
    else
        echo "external"
    fi
}

get_port_name() {
    local port="$1"
    echo "${PORT_NAMES[$port]:-}"
}

# ============================================================================
# Data Collection
# ============================================================================

collect_data() {
    # Conntrack stats
    CT_COUNT=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null) || CT_COUNT=0
    CT_MAX=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null) || CT_MAX=1
    CT_BUCKETS=$(cat /proc/sys/net/netfilter/nf_conntrack_buckets 2>/dev/null) || CT_BUCKETS=0

    if [[ "$CT_MAX" -gt 0 ]]; then
        CT_PCT=$(echo "scale=2; ($CT_COUNT / $CT_MAX) * 100" | bc 2>/dev/null) || CT_PCT="0"
    else
        CT_PCT="0"
    fi

    # OVS conntrack - check host first, then try containers
    OVS_CT=0
    OVS_SOURCE=""
    if command -v ovs-appctl &>/dev/null; then
        OVS_CT=$(ovs-appctl dpctl/dump-conntrack 2>/dev/null | wc -l) || OVS_CT=0
        [[ "$OVS_CT" -gt 0 ]] && OVS_SOURCE="host"
    fi
    # If not found on host, try isard-hypervisor container
    if [[ "$OVS_CT" -eq 0 ]] && command -v docker &>/dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "isard-hypervisor"; then
            OVS_CT=$(docker exec isard-hypervisor ovs-appctl dpctl/dump-conntrack 2>/dev/null | wc -l) || OVS_CT=0
            [[ "$OVS_CT" -gt 0 ]] && OVS_SOURCE="isard-hypervisor"
        fi
    fi
    # Try isard-vpn container if still not found
    if [[ "$OVS_CT" -eq 0 ]] && command -v docker &>/dev/null; then
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "isard-vpn"; then
            OVS_CT=$(docker exec isard-vpn ovs-appctl dpctl/dump-conntrack 2>/dev/null | wc -l) || OVS_CT=0
            [[ "$OVS_CT" -gt 0 ]] && OVS_SOURCE="isard-vpn"
        fi
    fi

    # Cache conntrack output for multiple parses
    CONNTRACK_DATA=$(conntrack -L 2>/dev/null) || CONNTRACK_DATA=""

    # Protocol counts using grep with fallback
    TCP_COUNT=$(echo "$CONNTRACK_DATA" | grep -c "^tcp" 2>/dev/null) || TCP_COUNT=0
    UDP_COUNT=$(echo "$CONNTRACK_DATA" | grep -c "^udp" 2>/dev/null) || UDP_COUNT=0
    ICMP_COUNT=$(echo "$CONNTRACK_DATA" | grep -c "^icmp" 2>/dev/null) || ICMP_COUNT=0

    # TCP states
    ESTABLISHED=$(echo "$CONNTRACK_DATA" | grep -c "ESTABLISHED" 2>/dev/null) || ESTABLISHED=0
    TIME_WAIT=$(echo "$CONNTRACK_DATA" | grep -c "TIME_WAIT" 2>/dev/null) || TIME_WAIT=0
    CLOSE_WAIT=$(echo "$CONNTRACK_DATA" | grep -c "CLOSE_WAIT" 2>/dev/null) || CLOSE_WAIT=0
    SYN_SENT=$(echo "$CONNTRACK_DATA" | grep -c "SYN_SENT" 2>/dev/null) || SYN_SENT=0
    SYN_RECV=$(echo "$CONNTRACK_DATA" | grep -c "SYN_RECV" 2>/dev/null) || SYN_RECV=0
    FIN_WAIT=$(echo "$CONNTRACK_DATA" | grep -c "FIN_WAIT" 2>/dev/null) || FIN_WAIT=0
    CLOSE=$(echo "$CONNTRACK_DATA" | grep -c " CLOSE " 2>/dev/null) || CLOSE=0

    # Issue detection
    UNREPLIED=$(echo "$CONNTRACK_DATA" | grep -c "UNREPLIED" 2>/dev/null) || UNREPLIED=0
    TABLE_FULL=$(dmesg 2>/dev/null | grep -c "nf_conntrack: table full" 2>/dev/null) || TABLE_FULL=0

    # Traffic classification
    INTERNAL_CT=$(echo "$CONNTRACK_DATA" | grep -cE "dst=(172\.|10\.|192\.168\.)" 2>/dev/null) || INTERNAL_CT=0
    LOCALHOST_CT=$(echo "$CONNTRACK_DATA" | grep -c "dst=127\." 2>/dev/null) || LOCALHOST_CT=0
    # For external, count total and subtract
    local total_ct
    total_ct=$(echo "$CONNTRACK_DATA" | wc -l) || total_ct=0
    EXTERNAL_CT=$((total_ct - INTERNAL_CT - LOCALHOST_CT))
    [[ $EXTERNAL_CT -lt 0 ]] && EXTERNAL_CT=0

    # GENEVE connections
    GENEVE_CT=$(echo "$CONNTRACK_DATA" | grep -c "dport=6081" 2>/dev/null) || GENEVE_CT=0

    # WireGuard connections (port 443 UDP)
    WG_CT=$(echo "$CONNTRACK_DATA" | grep "^udp" 2>/dev/null | grep -c "dport=443" 2>/dev/null) || WG_CT=0

    # DNS to systemd-resolved
    DNS_RESOLVED=$(echo "$CONNTRACK_DATA" | grep -c "dst=127.0.0.53" 2>/dev/null) || DNS_RESOLVED=0
}

# ============================================================================
# JSON Output
# ============================================================================

output_json() {
    local timestamp
    timestamp=$(date -Iseconds)

    # Build destinations array
    local destinations_json=""
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local container ip_type
            container=$(resolve_ip "$ip")
            ip_type=$(get_ip_type "$ip")
            destinations_json="${destinations_json}{\"ip\":\"$ip\",\"count\":$count,\"type\":\"$ip_type\",\"name\":\"$container\"},"
        done < <(echo "$CONNTRACK_DATA" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^dst=/) {
                    split($i, a, "=")
                    print a[2]
                }
            }
        }' | sort | uniq -c | sort -nr | head -20)
    fi
    destinations_json="[${destinations_json%,}]"

    # Build sources array
    local sources_json=""
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local container ip_type
            container=$(resolve_ip "$ip")
            ip_type=$(get_ip_type "$ip")
            sources_json="${sources_json}{\"ip\":\"$ip\",\"count\":$count,\"type\":\"$ip_type\",\"name\":\"$container\"},"
        done < <(echo "$CONNTRACK_DATA" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^src=/) {
                    split($i, a, "=")
                    print a[2]
                    break
                }
            }
        }' | sort | uniq -c | sort -nr | head -20)
    fi
    sources_json="[${sources_json%,}]"

    # Build ports array
    local ports_json=""
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count port; do
            [[ -z "$port" ]] && continue
            local service
            service=$(get_port_name "$port")
            ports_json="${ports_json}{\"port\":$port,\"count\":$count,\"service\":\"$service\"},"
        done < <(echo "$CONNTRACK_DATA" | grep -oP 'dport=\K\d+' | sort | uniq -c | sort -nr | head -20)
    fi
    ports_json="[${ports_json%,}]"

    # Build issues list
    local issues_list=""
    [[ "$UNREPLIED" -gt 100 ]] && issues_list="${issues_list}\"high_unreplied\","
    [[ "$TIME_WAIT" -gt 5000 ]] && issues_list="${issues_list}\"high_time_wait\","
    [[ "$DNS_RESOLVED" -gt 100 ]] && issues_list="${issues_list}\"high_dns_queries\","
    [[ "$TABLE_FULL" -gt 0 ]] && issues_list="${issues_list}\"table_full_errors\","
    if [[ $(echo "$CT_PCT > 80" | bc 2>/dev/null) == "1" ]]; then
        issues_list="${issues_list}\"conntrack_critical\","
    elif [[ $(echo "$CT_PCT > 60" | bc 2>/dev/null) == "1" ]]; then
        issues_list="${issues_list}\"conntrack_warning\","
    fi

    cat << EOF
{
  "timestamp": "$timestamp",
  "stats": {
    "netfilter": {"count": $CT_COUNT, "max": $CT_MAX, "percent": $CT_PCT, "buckets": $CT_BUCKETS},
    "ovs": {"count": $OVS_CT, "source": "$OVS_SOURCE"}
  },
  "protocols": {"tcp": $TCP_COUNT, "udp": $UDP_COUNT, "icmp": $ICMP_COUNT},
  "tcp_states": {
    "ESTABLISHED": $ESTABLISHED,
    "TIME_WAIT": $TIME_WAIT,
    "CLOSE_WAIT": $CLOSE_WAIT,
    "SYN_SENT": $SYN_SENT,
    "SYN_RECV": $SYN_RECV,
    "FIN_WAIT": $FIN_WAIT,
    "CLOSE": $CLOSE
  },
  "traffic": {
    "internal": $INTERNAL_CT,
    "localhost": $LOCALHOST_CT,
    "external": $EXTERNAL_CT,
    "geneve": $GENEVE_CT,
    "wireguard": $WG_CT
  },
  "destinations": $destinations_json,
  "sources": $sources_json,
  "ports": $ports_json,
  "issues": {
    "unreplied": $UNREPLIED,
    "table_full_errors": $TABLE_FULL,
    "dns_resolved": $DNS_RESOLVED,
    "list": [${issues_list%,}]
  }
}
EOF
}

# ============================================================================
# Text Output
# ============================================================================

output_text() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "  CONNECTION TRACKING ANALYSIS - $(date)"
    echo "═══════════════════════════════════════════════════════════════"
    echo

    # Overall Stats
    echo "┌─ OVERALL STATISTICS ──────────────────────────────────────────┐"
    printf "  Netfilter Conntrack: %s / %s (%s%%)\n" "$CT_COUNT" "$CT_MAX" "$CT_PCT"
    if [[ -n "$OVS_SOURCE" ]]; then
        printf "  OVS Conntrack:       %s entries (from %s)\n" "$OVS_CT" "$OVS_SOURCE"
    else
        printf "  OVS Conntrack:       %s entries\n" "$OVS_CT"
    fi
    printf "  Hash Buckets:        %s\n" "$CT_BUCKETS"
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Protocol Breakdown
    echo "┌─ PROTOCOL DISTRIBUTION ───────────────────────────────────────┐"
    printf "  TCP:       %6d connections\n" "$TCP_COUNT"
    printf "  UDP:       %6d connections\n" "$UDP_COUNT"
    printf "  ICMP:      %6d connections\n" "$ICMP_COUNT"
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Top Destinations
    echo "┌─ TOP 15 DESTINATIONS ─────────────────────────────────────────┐"
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local name
            name=$(resolve_ip "$ip")
            printf "  %5d  %-15s (%s)\n" "$count" "$ip" "$name"
        done < <(echo "$CONNTRACK_DATA" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^dst=/) {
                    split($i, a, "=")
                    print a[2]
                }
            }
        }' | sort | uniq -c | sort -nr | head -15)
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Top Sources
    echo "┌─ TOP 15 SOURCES ──────────────────────────────────────────────┐"
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local name
            name=$(resolve_ip "$ip")
            printf "  %5d  %-15s (%s)\n" "$count" "$ip" "$name"
        done < <(echo "$CONNTRACK_DATA" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^src=/) {
                    split($i, a, "=")
                    print a[2]
                    break
                }
            }
        }' | sort | uniq -c | sort -nr | head -15)
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Top Ports
    echo "┌─ TOP 15 DESTINATION PORTS ────────────────────────────────────┐"
    if [[ -n "$CONNTRACK_DATA" ]]; then
        while read -r count port; do
            [[ -z "$port" ]] && continue
            local service
            service=$(get_port_name "$port")
            if [[ -n "$service" ]]; then
                printf "  %5d  Port %-6s (%s)\n" "$count" "$port" "$service"
            else
                printf "  %5d  Port %s\n" "$count" "$port"
            fi
        done < <(echo "$CONNTRACK_DATA" | grep -oP 'dport=\K\d+' | sort | uniq -c | sort -nr | head -15)
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # TCP Connection States
    echo "┌─ TCP CONNECTION STATES ───────────────────────────────────────┐"
    printf "  ESTABLISHED:   %6d\n" "$ESTABLISHED"
    printf "  TIME_WAIT:     %6d\n" "$TIME_WAIT"
    printf "  CLOSE_WAIT:    %6d\n" "$CLOSE_WAIT"
    printf "  SYN_SENT:      %6d\n" "$SYN_SENT"
    printf "  SYN_RECV:      %6d\n" "$SYN_RECV"
    printf "  FIN_WAIT:      %6d\n" "$FIN_WAIT"
    printf "  CLOSE:         %6d\n" "$CLOSE"
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Traffic Classification
    echo "┌─ TRAFFIC CLASSIFICATION ──────────────────────────────────────┐"
    local total=$((INTERNAL_CT + LOCALHOST_CT + EXTERNAL_CT))
    if [[ "$total" -gt 0 ]]; then
        printf "  Internal (10.x/172.x/192.168.x): %5d (%3d%%)\n" "$INTERNAL_CT" "$((INTERNAL_CT * 100 / total))"
        printf "  Localhost (127.x):               %5d (%3d%%)\n" "$LOCALHOST_CT" "$((LOCALHOST_CT * 100 / total))"
        printf "  External (Internet):             %5d (%3d%%)\n" "$EXTERNAL_CT" "$((EXTERNAL_CT * 100 / total))"
    else
        echo "  No connections found"
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Docker-specific analysis
    echo "┌─ DOCKER-SPECIFIC ANALYSIS ────────────────────────────────────┐"
    local docker_count
    docker_count=$(echo "$CONNTRACK_DATA" | grep -cE "172\.(1[6-9]|2[0-9]|3[0-1])\." 2>/dev/null) || docker_count=0
    printf "  Docker subnet connections: %d\n" "$docker_count"
    printf "  DNS to systemd-resolved:   %d\n" "$DNS_RESOLVED"
    if [[ $DNS_RESOLVED -gt 100 ]]; then
        echo -e "  ${YELLOW}⚠️  WARNING: High DNS query count - possible resolution issues${RESET}"
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # GENEVE Tunnel Traffic
    echo "┌─ GENEVE TUNNEL TRAFFIC (Port 6081) ───────────────────────────┐"
    printf "  GENEVE connections: %d\n" "$GENEVE_CT"
    if [[ "$GENEVE_CT" -gt 0 ]]; then
        echo ""
        echo "  Top tunnel endpoints:"
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local name
            name=$(resolve_ip "$ip")
            printf "    %4d  %-15s (%s)\n" "$count" "$ip" "$name"
        done < <(echo "$CONNTRACK_DATA" | grep "dport=6081" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^dst=/) {
                    split($i, a, "=")
                    print a[2]
                }
            }
        }' | sort | uniq -c | sort -nr | head -10)
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # WireGuard Traffic
    echo "┌─ WIREGUARD TRAFFIC (Port 443 UDP) ────────────────────────────┐"
    printf "  WireGuard connections: %d\n" "$WG_CT"
    if [[ "$WG_CT" -gt 0 ]]; then
        echo ""
        echo "  Top WireGuard endpoints:"
        while read -r count ip; do
            [[ -z "$ip" ]] && continue
            local name
            name=$(resolve_ip "$ip")
            printf "    %4d  %-15s (%s)\n" "$count" "$ip" "$name"
        done < <(echo "$CONNTRACK_DATA" | grep "^udp" | grep "dport=443" | awk '{
            for(i=1; i<=NF; i++) {
                if($i ~ /^dst=/) {
                    split($i, a, "=")
                    print a[2]
                }
            }
        }' | sort | uniq -c | sort -nr | head -10)
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # Potential Issues
    echo "┌─ POTENTIAL ISSUES ────────────────────────────────────────────┐"
    printf "  UNREPLIED connections:     %d\n" "$UNREPLIED"
    if [[ "$UNREPLIED" -gt 100 ]]; then
        echo -e "  ${YELLOW}⚠️  High UNREPLIED count - possible connection issues${RESET}"
    fi

    printf "  TIME_WAIT connections:     %d\n" "$TIME_WAIT"
    if [[ "$TIME_WAIT" -gt 5000 ]]; then
        echo -e "  ${YELLOW}⚠️  High TIME_WAIT count - consider reducing timeout${RESET}"
    fi

    # Check if approaching limit
    if [[ $(echo "$CT_PCT > 80" | bc 2>/dev/null) == "1" ]]; then
        echo -e "  ${RED}🔴 CRITICAL: Conntrack usage above 80%!${RESET}"
    elif [[ $(echo "$CT_PCT > 60" | bc 2>/dev/null) == "1" ]]; then
        echo -e "  ${YELLOW}⚠️  WARNING: Conntrack usage above 60%${RESET}"
    fi

    # Check for table full errors
    if [[ "$TABLE_FULL" -gt 0 ]]; then
        echo -e "  ${RED}🔴 CRITICAL: $TABLE_FULL 'table full' errors in dmesg!${RESET}"
    fi
    echo "└───────────────────────────────────────────────────────────────┘"
    echo

    # OVS Info
    if [[ "$OVS_CT" -gt 0 ]]; then
        echo "┌─ OVS CONNTRACK INFO ────────────────────────────────────────┐"
        echo "  ℹ️  OVS has $OVS_CT tracked connections (implicit datapath tracking)"
        echo "  This is separate from netfilter conntrack and is normal."
        echo "└───────────────────────────────────────────────────────────────┘"
        echo
    fi

    echo "═══════════════════════════════════════════════════════════════"
    echo "  Analysis complete at $(date)"
    echo "═══════════════════════════════════════════════════════════════"
}

# ============================================================================
# Main
# ============================================================================

main() {
    setup_colors
    build_docker_mapping
    collect_data

    if [[ "$JSON_OUTPUT" == "true" ]]; then
        output_json
    else
        output_text
    fi
}

main
