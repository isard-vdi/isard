ssh-keygen -q -t rsa -N '' -f /root/.ssh/id_rsa
mkdir /root/.ssh
ssh-keyscan -p 2022 -t rsa -T 3 isard-hypervisor > /root/.ssh/known_hosts
sshpass -p $API_HYPERVISORS_SECRET ssh-copy-id -p 2022 root@isard-hypervisor
python3 run.py
