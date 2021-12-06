#!/bin/sh
#$1 - add 
#$2 - 52:54:00:2c:7a:13 
#$3 - 192.168.128.76 
#$4 - slax

export API_HYPERVISORS_SECRET=$API_HYPERVISORS_SECRET
/usr/bin/python3 /dnsmasq-hook/update-client-ips.py "$@"
