#!/bin/bash
rm -f /var/run/squid.pid
if [ ! -n "$VIDEO_HYPERVISOR_HOSTNAMES" ]; then
    HOSTS='isard-hypervisor'
else
    HOSTS=$(echo $VIDEO_HYPERVISOR_HOSTNAMES |tr "," " ")
fi

if [ ! -n "$VIDEO_HYPERVISOR_PORTS" ]; then
    PORTS='5900-7899'
else
    PORTS=$(echo $VIDEO_HYPERVISOR_PORTS |tr "," " ")
fi

cat <<EOT > /etc/squid/squid.conf
pid_filename none
read_timeout 120 minutes
half_closed_clients off

# A CONNECT is tunnelled only to a listed hypervisor AND a viewer port; a known
# hypervisor must not reach its own non-viewer ports (ssh, libvirt...).
acl SPICE_HOSTS dst $HOSTS
acl SPICE_PORTS port $PORTS
acl CONNECT method CONNECT
http_access allow CONNECT SPICE_HOSTS SPICE_PORTS
http_access deny all

# Reveal nothing about the proxy to the client or the client to the hypervisor.
# The error page body is blanked in the image; stripping the squid headers here
# leaves a denied CONNECT as an empty 403 with no fingerprint.
httpd_suppress_version_string on
via off
visible_hostname isard-squid
forwarded_for delete
reply_header_access Server deny all
reply_header_access X-Squid-Error deny all
reply_header_access Cache-Status deny all

http_port 8080

# This proxy only tunnels the viewer; it never caches.
cache deny all
cache_mem 0 MB
maximum_object_size 0 MB
digest_generation off

# One line per CONNECT to stdout, so the platform log pipeline keeps the audit
# trail (who tunnelled where, and every denied attempt).
logformat isardspice %ts.%03tu %>a %Ss/%03>Hs %rm %ru
access_log stdio:/dev/stdout isardspice
cache_log stdio:/dev/stderr
logfile_rotate 0
EOT

# Used by test_squid_conf.sh: write the config and stop, do not start squid.
if [ "$1" = "--generate-only" ]; then
    exit 0
fi

/usr/sbin/squid -NYCd 1
