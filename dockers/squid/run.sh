#!/bin/bash

if [ ! "$SPICE_HOSTS" == "false" ]; then
	HOSTS=$(echo $SPICE_HOSTS |tr "," " ")
        sed -i "/^acl SPICE_HOSTS/c\acl SPICE_HOSTS dst $HOSTS" /etc/squid/squid.conf
        sed -i "/^http_port/c\http_port $SPICE_PROXY_PORT" /etc/squid/squid.conf
        squid -N
else
	echo "SPICE_HOSTS=false in .env"
	echo "So exitting squid instance as not needed."
	echo "Access to viewer ports will be direct."
	exit 1
fi
