#!/bin/bash
public_key="/root/.ssh/authorized_keys"
if [ -f "$public_key" ]
then
	echo "$file found, so not generating new ones."
else
	echo "$file not found, generating new ones"
	cat /dev/zero | ssh-keygen -q -N ""
	mv /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys 
fi
ssh-keyscan isard-hypervisor > /root/.ssh/known_hosts
python3 /isard/run_engine.py
