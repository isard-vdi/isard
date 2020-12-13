FROM alpine:3.12.0 as production
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache --update wireguard-tools openssh
RUN rm -rf /etc/ssh/ssh_host_rsa_key /etc/ssh/ssh_host_dsa_key
COPY docker/vpn/wg0.conf /etc/wireguard/
COPY docker/vpn/run.sh /
CMD [ "sh", "run.sh"]

