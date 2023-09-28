#!/bin/sh

ssh_copy_keys() {
    rm -f /root/.ssh/id_rsa
    rm -f /root/.ssh/known_hosts
    ssh-keygen -q -t rsa -N '' -f /root/.ssh/id_rsa

    ssh-keyscan -p 2022 -t rsa -T 3 isard-hypervisor > /root/.ssh/known_hosts
    sshpass -p "$API_HYPERVISORS_SECRET" ssh-copy-id -p 2022 root@isard-hypervisor
}

if [ "$FLAVOUR" = "all-in-one" ] || [ "$FLAVOUR" = "hypervisor" ] || [ "$FLAVOUR" = "hypervisor-standalone" ] || [ "$FLAVOUR" = "" ]; then
    while [ -z "$( socat -T2 stdout tcp:isard-hypervisor:2022,connect-timeout=2,readbytes=1 2>/dev/null )" ]; do
        echo "Waiting for hypervisor sshd service to be up..."
        sleep 2
    done
    sleep 2

    if [ ! -f /root/.ssh/id_rsa ]; then
        ssh_copy_keys
    fi

    until ssh -p 2022 root@isard-hypervisor "test -e /var/run/libvirt/libvirt-sock-ro" > /tmp/libvirt.log 2>&1; do
        # Copy keys if they are missing
        if grep -q "Permission denied, please try again." /tmp/libvirt.log; then
            ssh_copy_keys

        # Copy keys if the hypervisor has changed keys
        elif grep -q "WARNING" /tmp/libvirt.log; then
            ssh_copy_keys

        else
            echo "Waiting for libvirt service to be started"
            sleep 2
        fi
    done
fi

if [ -n "$TF_VAR_private_key" ]; then
    export TF_VAR_private_key_path=/oci-private.key
    echo "$TF_VAR_private_key" > $TF_VAR_private_key_path
fi

/stats
