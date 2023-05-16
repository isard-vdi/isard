#!/bin/bash
rm -f /var/run/squid.pid
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
# Disable cache
echo "cache deny all" >> /etc/squid/squid.conf
echo "cache_dir null /tmp" >> /etc/squid/squid.conf
echo "cache_store_log none" >> /etc/squid/squid.conf
echo "cache_log /dev/null" >> /etc/squid/squid.conf
echo "cache_access_log /var/log/squid/access.log" >> /etc/squid/squid.conf
echo "cache_mem 0 MB" >> /etc/squid/squid.conf
echo "logfile_rotate 0" >> /etc/squid/squid.conf
echo "maximum_object_size 0 MB" >> /etc/squid/squid.conf
echo "maximum_object_size_in_memory 0 KB" >> /etc/squid/squid.conf
echo "store_objects_per_bucket 20" >> /etc/squid/squid.conf
echo "digest_generation off" >> /etc/squid/squid.conf
#echo "<html><body><script>window.onload = function() {window.location.protocol === 'http:' && (location.href = location.href.replace(/^http:/, 'https:'));</script></body></html>" > /usr/share/squid/errors/REDIRECT
squid -NYCd 1
