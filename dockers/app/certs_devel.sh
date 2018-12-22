#!/bin/bash
#public_key="/root/.ssh/authorized_keys"
#if [ -f "$public_key" ]
#then
#	echo "$file found, so not generating new ones."
#else
#	echo "$file not found, generating new ones"
cat /dev/zero | ssh-keygen -q -N ""
mv /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys 

#fi
#ssh-keyscan isard-hypervisor > /tmp/known_hosts
#DIFF=$(diff /root/.ssh/know_hosts /tmp/known_hosts) 
#if [ "$DIFF" != "" ] 
#then
#    	echo "The HYPERVISOR key has been regenerated"
#	rm /root/.ssh/known_hosts

echo "Scanning isard-hypervisor key..."
ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
while [ ! -s /root/.ssh/known_hosts ]
do
  sleep 2
  echo "Waiting for isard-hypervisor to be online..."
  ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
done
echo "isard-hypervisor online, starting engine..."

#fi

######## Only on development
echo -e "isard\nisard" | (passwd --stdin root)
####echo -e "isard\nisard" | passwd root
ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N ''
#ssh-keygen -t rsa -f /etc/ssh/ssh_host_rsa_key -N ''
#/usr/sbin/sshd 
########

#!/bin/bash
cd /isard
#not run in devel
#git pull
#python3 run_webapp.py & python3 run_engine.py & sleep 1000000
