#!/bin/sh

if [ "$FLAVOUR" == "all-in-one" ] || [ "$FLAVOUR" == "hypervisor" ] || [ "$FLAVOUR" == "hypervisor-standalone" ]; then
    while [ -z "$( socat -T2 stdout tcp:isard-hypervisor:2022,connect-timeout=2,readbytes=1 2>/dev/null )" ]
    do
        echo "Waiting for hypervisor sshd service to be up..."
        sleep 2
    done
    sleep 2

    if [ ! -f /root/.ssh/id_rsa ]; then
        ssh-keygen -q -t rsa -N '' -f /root/.ssh/id_rsa
    fi

    ssh-keyscan -p 2022 -t rsa -T 3 isard-hypervisor > /root/.ssh/known_hosts
    sshpass -p $API_HYPERVISORS_SECRET ssh-copy-id -p 2022 root@isard-hypervisor
fi

/stats
