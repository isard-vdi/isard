apt install firewalld fail2ban -y

#echo "Setting iptables to not use nf_tables"
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
#update-alternatives --set iptables /usr/sbin/iptables-legacy

echo "Setting docker to not open ports automatically..."
echo '{ "iptables": false }' > /etc/docker/daemon.json

cp 01* /etc/fail2ban/fail2ban.d/

echo "Setting firewalld to use iptables..."
sed -i 's/FirewallBackend=nftables/FirewallBackend=iptables/g' /etc/firewalld/firewalld.conf

rm -rf /etc/firewalld/zones/*
firewall-cmd --permanent --zone=public --change-interface=docker0 
firewall-cmd --permanent --zone=public --add-masquerade
# This assumes a typical port 22 for ssh. If not just set it here with --add-port
firewall-cmd --permanent --zone=public --add-service=ssh

## OUTSIDE WORLD NEEDED PORTS FOR ISARDVDI WEB and VIEWERS
firewall-cmd --permanent --zone=public --add-port=443/tcp
firewall-cmd --permanent --zone=public --add-port=80/tcp

## LETS RESTART EVERYTHING.
systemctl restart firewalld
systemctl stop docker
systemctl start docker
systemctl restart fail2ban

