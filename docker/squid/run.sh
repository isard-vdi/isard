#!/bin/bash
if [ ! -n "$VIDEO_HYPERVISOR_HOSTNAMES" ]; then
    HOSTS='isard-hypervisor'
else
    HOSTS=$(echo $VIDEO_HYPERVISOR_HOSTNAMES |tr "," " ")
fi

if [ ! -n "$VIDEO_HYPERVISOR_PORTS" ]; then
    VIDEO_HYPERVISOR_PORTS='5900-6900'
fi

echo "read_timeout 120 minutes" > /etc/squid/squid.conf
echo "half_closed_clients on" >> /etc/squid/squid.conf
echo "acl SPICE_HOSTS dst $HOSTS" >> /etc/squid/squid.conf
echo "acl SPICE_PORTS dst $VIDEO_HYPERVISOR_PORTS" >> /etc/squid/squid.conf
echo "acl CONNECT method CONNECT" >> /etc/squid/squid.conf
echo "http_access allow SPICE_HOSTS" >> /etc/squid/squid.conf
echo "http_access allow SPICE_PORTS" >> /etc/squid/squid.conf
echo "http_access deny CONNECT !SPICE_PORTS" >> /etc/squid/squid.conf
#echo "deny_info REDIRECT all" >> /etc/squid/squid.conf
echo "http_access deny all" >> /etc/squid/squid.conf
echo "http_port 8080" >> /etc/squid/squid.conf

#echo "<html><body><script>window.onload = function() {window.location.protocol === 'http:' && (location.href = location.href.replace(/^http:/, 'https:'));</script></body></html>" > /usr/share/squid/errors/REDIRECT

sleep 5
squid -N
