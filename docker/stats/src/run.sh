#!/bin/sh

if [ ! -n "$STATS_HYP_HOSTNAME" ]; then
        export STATS_HYP_HOSTNAME='isard-hypervisor'
fi
if [ ! -n "$STATS_HYP_PORT" ]; then
        export STATS_HYP_PORT='2022'
fi
if [ ! -n "$STATS_HYP_USER" ]; then
        export STATS_HYP_USER='root'
fi

while [ -z "$( socat -T2 stdout tcp:$STATS_HYP_HOSTNAME:$STATS_HYP_PORT,connect-timeout=2,readbytes=1 2>/dev/null )" ]
do
    echo "Waiting for hypervisor sshd service to be up..."
    sleep 2
done
echo "Service sshd ready in hypervisor."
## Whe should wait for hypervisor to have libvirtd started.
## One way could be to use api_client here and wait for hyper to be online.
sleep 40

rm -rf /root/.ssh
mkdir /root/.ssh
ssh-keygen -q -t rsa -N '' -f /root/.ssh/id_rsa
echo "ssh-keyscan -p $STATS_HYP_PORT -t rsa -T 3 $STATS_HYP_HOSTNAME"
ssh-keyscan -p $STATS_HYP_PORT -t rsa -T 3 $STATS_HYP_HOSTNAME > /root/.ssh/known_hosts
echo "sshpass -p XXXXXX ssh-copy-id -p $STATS_HYP_PORT $STATS_HYP_USER@$STATS_HYP_HOSTNAME"
sshpass -p $API_HYPERVISORS_SECRET ssh-copy-id -p $STATS_HYP_PORT $STATS_HYP_USER@$STATS_HYP_HOSTNAME
python3 run.py
