#!/bin/bash

if [ ! "$SPICE_HOSTS" == "false" ]; then
	$HOSTS=$(echo $SPICE_HOSTS |tr "," " ")
        sed -i "/^acl SPICE_HOSTS/c\acl SPICE_HOSTS dst $HOSTS" /etc/squid/squid.conf
        sed -i "/^http port/c\http port $SPICE_PROXY_PORT" /etc/squid/squid.conf
        squid -N
else
	echo "No proxy config found"
	exit 1
fi
