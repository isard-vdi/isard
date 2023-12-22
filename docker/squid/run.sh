#!/bin/bash
rm -f /var/run/squid.pid
if [ ! -n "$VIDEO_HYPERVISOR_HOSTNAMES" ]; then
    HOSTS='isard-hypervisor'
else
    HOSTS=$(VIDEO_HYPERVISOR_HOSTNAMES |tr "," " ")
fi

if [ ! -n "$VIDEO_HYPERVISOR_PORTS" ]; then
    VIDEO_HYPERVISOR_PORTS='5900-7899'
fi

cat <<EOT > /etc/squid/squid.conf
pid_filename none
read_timeout 120 minutes
half_closed_clients on
acl SPICE_HOSTS dst $HOSTS
acl SPICE_PORTS dst $VIDEO_HYPERVISOR_PORTS
acl CONNECT method CONNECT
http_access allow SPICE_HOSTS
http_access allow SPICE_PORTS
http_access deny CONNECT !SPICE_PORTS
http_access deny all
http_port 8080
cache deny all
cache_dir null /tmp
cache_store_log none
cache_log /dev/null
cache_access_log /var/log/squid/access.log
cache_mem 0 MB
logfile_rotate 0
maximum_object_size 0 MB
maximum_object_size_in_memory 0 KB
store_objects_per_bucket 20
digest_generation off
EOT

/usr/sbin/squid -NYCd 1