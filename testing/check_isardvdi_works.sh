#!/usr/bin/env bash

set -e

if [ -n "$DEBUG" ]; then
    set -x
fi

HOST="${HOST-https://localhost}"
USERNAME="${USERNAME-admin}"
PASSWORD="${PASSWORD-IsardVDI}"
DESKTOP_ID="${DESKTOP_ID-_local-default-admin-admin_downloaded_slax93}"


ORIGINAL_WD=$(pwd)
TMP_WD=$(mktemp -d)

check_dependencies() {
    requirements="isardvdi-cli jq wg-quick ping remote-viewer remmina"
    for i in $requirements; do
        if ! which "$i" > /dev/null; then
            echo ""
            echo "REQUIREMENT: $i not found in the system"

            if [ "$i" == "isardvdi-cli" ]; then
                echo "You can install it from https://gitlab.com/isard/isardvdi-cli"
            fi
            exit 1
        fi
    done
}

test_failed() {
    # Ensure the wireguard interface is stopped
    wg-quick down ./isard.conf &> /dev/null || true

    echo "FAILED. You can check temporary files at $TMP_WD"
    cd $ORIGINAL_WD
    exit 1
}

login() {
    echo "host = \"$HOST\"
ignore_certs = true" > cli.toml

    isardvdi-cli auth form -u "$USERNAME" -p "$PASSWORD"
}

check_desktop() {
    if ! isardvdi-cli --json desktop list | jq -e ".[] | select(.id==\"$DESKTOP_ID\")" > /dev/null; then
        echo "ERROR: Slax is not installed! Please download it!"
        return 1
    fi
}

start_desktop() {
    isardvdi-cli desktop start --id "$DESKTOP_ID" > /dev/null
}

stop_desktop() {
    isardvdi-cli desktop stop --id "$DESKTOP_ID" > /dev/null
}

check_desktop_state() {
    state=""
    for i in {0..30}; do
        if isardvdi-cli --json desktop get --id="$DESKTOP_ID" | jq -e "select(.state==\"$1\")" > /dev/null; then
            return
        fi

        sleep 1
    done

    echo "ERROR: Desktop in not correct state! Expecting: $1, desktop state: $state"
    return 1
}

check_desktop_started() {
    check_desktop_state "Started" || return 1
}

check_desktop_stopped() {
    check_desktop_state "Stopped" || return 1
}

test_vpn() {
    isardvdi-cli vpn > isard.conf
    wg-quick up ./isard.conf &> /dev/null
    ip=$(isardvdi-cli desktop get --id "$DESKTOP_ID" --json | jq -r ".ip")

    if [[ -z "$ip" || "$ip" == "null" ]]; then
        echo "The desktop is started but doesn't have a IP address! Maybe it's missing the WireGuard network interface"
        return 1
    fi

    ping -c 1 $ip > /dev/null
}

test_viewer() {
    $1 &> viewer.out &
    pid=$!

    for i in {0..60}; do
        started=$(grep "$2" viewer.out -c) || true

        if [[ "$started" == "1" ]]; then
            kill -9 $pid
            wait $pid 2> /dev/null
            rm -f viewer.out
            return
        fi

        sleep 1
    done

    kill -9 $pid
    wait $pid 2> /dev/null

    echo "Viewer test failed: $1: timeout"
    return 1
}


test_spice() {
    isardvdi-cli desktop viewer --type spice --id "$DESKTOP_ID" > console.vv

    test_viewer "remote-viewer console.vv --spice-debug" "display-2:0: connect ready" || return 1
}

test_rdp() {
    isardvdi-cli desktop viewer --type rdp --id "$DESKTOP_ID" > console.rdp

    export G_MESSAGES_PREFIXED=all
    export G_MESSAGES_DEBUG=all

    test_viewer "remmina ./console.rdp" "(remmina_rdp_OnChannelConnectedEventHandler) - Channel drdynvc has been opened" || return 1
}

list_hypervisors() {
    isardvdi-cli hypervisor list --json | jq -r '[.[].id] | join(" ")'
}

force_hypervisor() {
    isardvdi-cli desktop update --id $DESKTOP_ID --forced-hyp $1
}

echo "Running tests..."
check_dependencies

cd $TMP_WD

echo "[1/2] Attempting to login..."
login || test_failed

echo "[2/2] Check if the desktop is downloaded..."
check_desktop || test_failed

for hyper in "$(list_hypervisors)"; do
    echo -e "\nRunning tests in hypervisor '$hyper'..."

    force_hypervisor $hyper 1> /dev/null || test_failed

    echo "[1/7] Start the desktop..."
    start_desktop || test_failed

    echo "[2/7] Check that the desktop starts successfully..."
    check_desktop_started || test_failed

    echo "[3/7] Test VPN connection..."
    test_vpn || test_failed

    echo "[4/7] Test the SPICE viewer..."
    test_spice || test_failed

    echo "[5/7] Test the RDP viewer..."
    test_rdp || test_failed

    echo "[6/7] Stop the desktop..."
    stop_desktop || test_failed

    echo "[7/7] Check that the desktop stops successfully..."
    check_desktop_stopped || test_failed

    wg-quick down ./isard.conf &> /dev/null
done

cd $ORIGINAL_WD
rm -rf $TMP_WD
echo ""
echo "All tests passed successfully! IsardVDI works! :)"
