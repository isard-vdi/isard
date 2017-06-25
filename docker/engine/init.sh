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
ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
#fi
python3 /isard/run_docker_engine.py
