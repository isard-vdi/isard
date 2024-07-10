# Hack to be able to use an arg as a COPY --from
# https://stackoverflow.com/a/63472135
ARG DOCKER_IMAGE_PREFIX=registry.gitlab.com/isard/isardvdi/
ARG DOCKER_IMAGE_TAG
FROM ${DOCKER_IMAGE_PREFIX}rdpgw:$DOCKER_IMAGE_TAG as rdpgw

#
# VPN
#
FROM alpine:3.20 as production
MAINTAINER isard <info@isardvdi.com>

RUN apk -U upgrade --no-cache

RUN apk add --no-cache \
    wireguard-tools \
    openssh \
    openvswitch \
    dnsmasq \
    # For WireGuard and others
    iptables \
    # For python-iptables
    iptables-legacy \
    # For guacd (RDP Web)
    guacamole-server \
    guacamole-server-dev \
    guacamole-server-rdp \
    # For RDP stats
    conntrack-tools \
    # For the aplication itself
    python3 \
    py3-pip

# OpenSSH
RUN rm -rf /etc/ssh/ssh_host_rsa_key /etc/ssh/ssh_host_dsa_key

# OpenVSwitch
RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/
COPY docker/vpn/ovs /ovs

# VPN
RUN pip3 install --break-system-package --no-cache-dir --upgrade pip
COPY docker/vpn/requirements.txt /requirements.txt
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \ 
    autoconf \
    automake \
    libtool \
    libmnl-dev \
    libnftnl-dev \
    git && \
    pip3 install --break-system-package --no-cache-dir  -r requirements.txt && \
    apk del .build_deps

# Required for python-iptables
ENV XTABLES_LIBDIR=/usr/lib/xtables

COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /

COPY --from=rdpgw /rdpgw /rdpgw

CMD [ "sh", "run.sh"]
