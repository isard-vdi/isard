# Hack to be able to use an arg as a COPY --from
# https://stackoverflow.com/a/63472135
ARG DOCKER_IMAGE_PREFIX=registry.gitlab.com/isard/isardvdi/
ARG DOCKER_IMAGE_TAG
FROM ${DOCKER_IMAGE_PREFIX}rdpgw:$DOCKER_IMAGE_TAG as rdpgw

FROM alpine:3.14.0 as production
MAINTAINER isard <info@isardvdi.com>

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
RUN git clone -b v1.8.7 git://git.netfilter.org/iptables
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
COPY docker/vpn/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN apk add libwebsockets@edge guacamole-server@testing guacamole-server-dev@testing freerdp freerdp-plugins

RUN apk add openvswitch
RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/
COPY docker/vpn/ovs /ovs

RUN apk add dnsmasq
COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /
# COPY docker/vpn/networking.py /

COPY --from=rdpgw /rdpgw /rdpgw

CMD [ "sh", "run.sh"]

