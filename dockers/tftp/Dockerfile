# Use Alpine Linux as base image
FROM alpine:3.8

# Install all the required packages
RUN apk add --update --no-cache tftp-hpa

# Expose the required ports
EXPOSE 69:69/udp

# Run the service
CMD [ "in.tftpd",  "-L", "--secure", "/var/tftpboot" ]
