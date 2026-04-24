#!/bin/sh
# Set process priorities for hypervisor services
# Ensures management daemons (sshd, libvirtd) can preempt QEMU processes
# Run after all daemons are started

echo "---> Setting process priorities..."

# Tier 1: Critical Management (-15)
# sshd - Engine's SSH entry point
for pid in $(pgrep -f '/usr/sbin/sshd'); do
    renice -n -15 -p $pid 2>/dev/null && echo "sshd ($pid): nice -15"
done

# libvirtd - Must respond to engine commands
for pid in $(pgrep -x libvirtd); do
    renice -n -15 -p $pid 2>/dev/null && echo "libvirtd ($pid): nice -15"
done

# Tier 2: Infrastructure (-10)
# virtlogd - Libvirt logging
for pid in $(pgrep -x virtlogd); do
    renice -n -10 -p $pid 2>/dev/null && echo "virtlogd ($pid): nice -10"
done

# ovsdb-server - OVS database
for pid in $(pgrep -x ovsdb-server); do
    renice -n -10 -p $pid 2>/dev/null && echo "ovsdb-server ($pid): nice -10"
done

# Tier 3: Network Services (-5)
# ovs-vswitchd - Virtual switch
for pid in $(pgrep -x ovs-vswitchd); do
    renice -n -5 -p $pid 2>/dev/null && echo "ovs-vswitchd ($pid): nice -5"
done

# ovs-worker.py - Flow management
for pid in $(pgrep -f 'ovs-worker.py'); do
    renice -n -5 -p $pid 2>/dev/null && echo "ovs-worker ($pid): nice -5"
done

echo "Process priorities configured"
