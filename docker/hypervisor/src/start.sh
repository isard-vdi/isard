#!/bin/sh
remove_hyper()
{
  if [ $HOSTNAME == "localhost" ]; then
    HOSTNAME="isard-hypervisor"
    URL="http://isard-api:7039/api/v2/hypervisor/$HOSTNAME"
    
  else
    URL="https://$WEPAPP_DOMAIN/debug/api/api/v2/hypervisor/$HOSTNAME"
  fi
  echo "Caught Signal ... removing hyper."
  curl --request DELETE \
  --url $URL \
  --user admin:$WEBAPP_ADMIN_PWD \
  --header "Content-Type: application/json" \
  -k
  echo "Done removing hyper ... quitting."
  exit 1
}
trap remove_hyper SIGTERM SIGINT SIGQUIT 

echo "---> Cleaning old libvirt info dirs..."
rm -rf /run/libvirt/*
rm -r /var/lib/libvirt/dnsmasq

ln -s /src/lib/api_client.py /src/certificates/api_client.py
ln -s /src/lib/api_client.py /src/vlans/api_client.py
ln -s /src/lib/api_client.py /src/dnsmasq-hook/api_client.py

echo "---> Setting ssh password to WEBAPP_ADMIN_PWD"
echo "root:$WEBAPP_ADMIN_PWD" |chpasswd

echo "---> Starting sshd server..."
ssh-keygen -A -f /usr/local/
/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config &

echo "---> Setting up hypervisor certificates from api..."
python3 /src/certificates/certificates.py
chmod 440 /etc/pki/libvirt-spice/*
chown qemu:root /etc/pki/libvirt-spice/*

echo "---> Setting up hypervisor wireguard guest network $WG_HYPER_GUESTNET..."
python3 /src/wireguard/wireguard.py
env > /tmp/env # This is needed by the dnsmasq-hook to get the envvars
# This is the route needed, should be added from above python script
#ip r a $WG_USERS_NET via ${WG_HYPER_NET_WG_PEER}

echo "---> Starting libvirt daemon..."
chown root:kvm /dev/kvm
/usr/sbin/virtlogd &
sleep 2
/usr/sbin/libvirtd &
sleep 1

echo "---> Setting vlans..."
sh -c "/src/vlans/vlans-discover.sh"

FILES=/etc/libvirt/qemu/networks/*
for f in $FILES
do
  filename=$(basename -- "$f")
  filename="${filename%.*}"
  if [ $filename != "autostart" ]; then
    echo "Activating network: $filename"
    /usr/bin/virsh net-start $filename
    /usr/bin/virsh net-autostart $filename
  fi
done

echo "---> Securing network connections from guests..."
iptables -I FORWARD -o eth0 -d $(ip -o -4 addr show dev eth0 | awk '{print $4}') -j REJECT

echo "---> Checking hypervisor by creating/destroying test domain..."
virsh create /src/checks/domain.xml
virsh destroy domain

echo "---> HYPERVISOR READY <---"
while true
do
    sleep 5
done

