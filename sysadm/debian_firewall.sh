#!/bin/bash

apt install firewalld fail2ban -y
# Fixes bug in iptables 1.8
echo "deb http://deb.debian.org/debian buster-backports main" > /etc/apt/sources.list.d/buster-backports.list
apt update
apt install -y iptables -t buster-backports

#echo "Setting iptables to not use nf_tables"
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
#update-alternatives --set iptables /usr/sbin/iptables-legacy

cp 01* /etc/fail2ban/fail2ban.d/

echo "Setting firewalld to use iptables..."
sed -i 's/FirewallBackend=nftables/FirewallBackend=iptables/g' /etc/firewalld/firewalld.conf

## LETS RESTART EVERYTHING.
systemctl restart firewalld
systemctl stop docker
systemctl start docker
systemctl restart fail2ban
