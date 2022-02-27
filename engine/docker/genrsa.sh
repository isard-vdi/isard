#!/bin/sh

# Set engine keys
if [ ! -f /root/.ssh/id_rsa ]
then
    echo "Generating new rsa keys..."
    cat /dev/zero | ssh-keygen -q -N ""

    echo -e "Host isard-hypervisor\n \
        StrictHostKeyChecking no" >/root/.ssh/config
    chmod 600 /root/.ssh/config

    echo "Checking for isard-hypervisor ssh..."

    i=0
    while ! nc -z isard-hypervisor 22; do   
      sleep 0.5
      ((i++))
      if [[ "$i" == '25' ]]; then
        break
      fi  
      echo "Checking for isard-hypervisor shh"
    done

    echo "Adding isard-hypervisor keys"
    ssh-keyscan -T 10 isard-hypervisor > /root/.ssh/known_hosts
fi
