#!/bin/bash

apt install firewalld fail2ban -y
# Fixes bug in iptables 1.8
echo "deb http://deb.debian.org/debian buster-backports main" > /etc/apt/sources.list.d/buster-backports.list
apt update
apt install -y iptables -t buster-backports

#echo "Setting iptables to not use nf_tables"
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy

echo "Setting docker to not open ports automatically..."
echo '{"iptables": true, "ipv6": false, "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" }}' > /etc/docker/daemon.json

cp 01* /etc/fail2ban/fail2ban.d/

echo "Setting firewalld to use iptables..."
sed -i 's/FirewallBackend=nftables/FirewallBackend=iptables/g' /etc/firewalld/firewalld.conf

rm -rf /etc/firewalld/zones/*
firewall-cmd --permanent --zone=public --change-interface=docker0 

# This assumes a typical port 22 for ssh. If not just set it here with --add-port
firewall-cmd --permanent --zone=public --add-service=ssh

# OUTSIDE WORLD NEEDED PORTS FOR ISARDVDI WEB and VIEWERS
firewall-cmd --permanent --zone=public --add-port=80/tcp
firewall-cmd --permanent --zone=public --add-port=443/tcp

# OUTSIDE WORLD WIREGUARD VPN
firewall-cmd --permanent --zone=public --add-port=443/udp

# OUTSIDE WORLD REMOTE HYPERVISORS VPN
firewall-cmd --permanent --zone=public --add-port=4443/udp

# If you want to map RDP directly to hypervisor (.17) without VPN:
#DOCKER_NET=172.18.255
#firewall-cmd --permanent --add-forward-port=port=21000-22000:proto=tcp:toport=21000-22000:toaddr={}.17

# LETS RESTART EVERYTHING.
systemctl restart firewalld
systemctl stop docker
systemctl start docker
systemctl restart fail2ban

