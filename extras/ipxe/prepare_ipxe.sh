#!/bin/sh

# Create the directories structure
mkdir -p /opt/isard/ipxe/conf/dhcpd
mkdir /opt/isard/ipxe/conf/ipxe
mkdir /opt/isard/logs/

# Copy the DHCP configuration example
cp ./dhcpd.conf.example /opt/isard/ipxe/conf/dhcpd/dhcpd.conf

# Create the logs file (this is done to prevent Docker Compose creating it as a directory)
touch /opt/isard/logs/ipxe.log

# Create the iPXE configuration (this is done to prevent Docker Compose creating it as a directory)
touch /opt/isard/ipxe/conf/ipxe/config.yml

# Show messages
echo "Final steps:"
echo "1- Edit /opt/isard/ipxe/conf/dhcpd/dhcpd.conf"
echo "2- Start Isard (docker-compose up -d)"
echo "3- Edit /opt/isard/ipxe/conf/ipxe/config.yml"
echo "4- Enjoy! You probably will need to wait for the images to download"
