# Use Alpine Linux as base image
FROM alpine:3.8
# Based on https://github.com/fabriziotorelli-wipro/nfs4-server

# Install all the required packages
RUN apk add --update --no-cache nfs-utils
RUN mkdir -p /nfs/images
ADD exports /etc/

# Expose the required ports
EXPOSE 111:111/udp 2049:2049/tcp

ADD entrypoint.sh /
RUN chmod 777 /entrypoint.sh

# Run the service
CMD ["/entrypoint.sh"]
