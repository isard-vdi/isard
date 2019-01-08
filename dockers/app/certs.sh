#!/bin/bash
public_key="/root/.ssh/authorized_keys"
if [ -f "$public_key" ]
then
    echo "$public_key found, so not generating new ones."
else
    echo "$public_key not found, generating new ones."
    cat /dev/zero | ssh-keygen -q -N ""
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

    echo "Scanning isard-hypervisor key..."
    ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
    while [ ! -s /root/.ssh/known_hosts ]
    do
      sleep .5
      echo "Waiting for isard-hypervisor to be online..."
      ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
    done
    echo "isard-hypervisor online..."
fi
