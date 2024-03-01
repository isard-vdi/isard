# Hack to be able to use an arg as a COPY --from
# https://stackoverflow.com/a/63472135
ARG DOCKER_IMAGE_PREFIX=registry.gitlab.com/isard/isardvdi/
ARG DOCKER_IMAGE_TAG
FROM ${DOCKER_IMAGE_PREFIX}rdpgw:$DOCKER_IMAGE_TAG as rdpgw

FROM alpine:3.18 as production
MAINTAINER isard <info@isardvdi.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache --update wireguard-tools openssh python3
RUN rm -rf /etc/ssh/ssh_host_rsa_key /etc/ssh/ssh_host_dsa_key

## From isard-api
RUN apk add python3 py3-pip
RUN pip3 install --upgrade pip
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
    git

# python-iptables
# Avoid temporary build errors of iptables master branch by setting iptables version.
# RUN git clone -b v1.8.7 git://git.netfilter.org/iptables
RUN git clone https://gitlab.com/isard/iptables.git
WORKDIR /iptables
RUN ./autogen.sh
RUN ./configure --prefix=/tmp/iptables
RUN make
RUN make install
WORKDIR /
RUN rm -rf iptables

ENV IPTABLES_LIBDIR=/tmp/iptables/lib
ENV XTABLES_LIBDIR=/tmp/iptables/lib/xtables

# python requirements
COPY docker/vpn/requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt
RUN apk del .build_deps

# Install guacd and freerdp
RUN echo -e "https://dl-cdn.alpinelinux.org/alpine/edge/main\n\
https://dl-cdn.alpinelinux.org/alpine/edge/community\n\
https://dl-cdn.alpinelinux.org/alpine/edge/testing" > /etc/apk/repos_edge
RUN apk add --repositories-file=/etc/apk/repos_edge guacamole-server guacamole-server-dev freerdp freerdp-libs freerdp-plugins

RUN apk add openvswitch
RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/
COPY docker/vpn/ovs /ovs

RUN apk add --repositories-file=/etc/apk/repos_edge dnsmasq
RUN apk add conntrack-tools
COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /
# COPY docker/vpn/networking.py /

COPY --from=rdpgw /rdpgw /rdpgw

CMD [ "sh", "run.sh"]
