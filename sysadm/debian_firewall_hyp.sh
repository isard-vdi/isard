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
firewall-cmd --zone=public --add-masquerade --permanent

firewall-cmd --zone=public --change-interface=docker0
firewall-cmd --zone=public --add-masquerade

firewall-cmd --zone=public --add-service=ssh --permanent
firewall-cmd --zone=public --remove-service=cockpit --permanent

firewall-cmd --zone=public --add-service=ssh
firewall-cmd --zone=public --remove-service=cockpit

## OUTSIDE WORLD NEEDED PORTS FOR ISARDVDI
firewall-cmd --zone=public --add-port=443/tcp --permanent
firewall-cmd --zone=public --add-port=80/tcp --permanent

firewall-cmd --zone=public --add-port=443/tcp
firewall-cmd --zone=public --add-port=80/tcp 

firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="<REMOTE HYPER IP>" port protocol="tcp" port="2022" accept'
firewall-cmd --add-rich-rule='rule family="ipv4" source address="<REMOTE HYPER IP>" port protocol="tcp" port="2022" accept'

systemctl restart firewalld
systemctl stop docker
systemctl start docker
systemctl restart fail2ban

