# Use Alpine Linux as base image
FROM alpine:3.8

# Install all the required packages
RUN apk add --update --no-cache dhcp

# Create the dhcpd.leases file
RUN touch /var/lib/dhcp/dhcpd.leases

# Expose the required ports
EXPOSE 67:67/udp

# Run the service
CMD [ "/usr/sbin/dhcpd",  "-4", "-d", "--no-pid", "-cf", "/etc/dhcpd/dhcpd.conf" ]
