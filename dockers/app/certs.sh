#!/bin/bash

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

# Remove all isard-hypervisor lines from known_hosts
sed -i '/isard-hypervisor/d' /root/.ssh/known_hosts

# If no id_rsa.pub key yet, create new one
auth_keys="/root/.ssh/id_rsa.pub"
if [ -f "$auth_keys" ]
then
    echo "$auth_keys found, so not generating new ones."
else
    echo "$auth_keys not found, generating new ones."
    cat /dev/zero | ssh-keygen -q -N ""
fi

#Copy new host key to authorized_keys (so isard-hypervisor can get it also)
cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys
    
# Now scan for isard-hypervisor for 10 seconds (should be more than enough)
echo "Scanning isard-hypervisor key..."
ssh-keyscan -T 10 isard-hypervisor > /root/.ssh/known_hosts
