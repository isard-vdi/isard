ARG GOLANG_BUILD_IMAGE

# Build rdpgw binary
FROM ${GOLANG_BUILD_IMAGE} as rdpgw-build

WORKDIR /build

RUN mkdir -p /build/pkg/sdk

COPY go.mod /build
COPY go.sum /build
COPY pkg/sdk/go.mod /build/pkg/sdk
COPY pkg/sdk/go.sum /build/pkg/sdk

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY rdpgw /build/rdpgw

WORKDIR /build/rdpgw

RUN CGO_ENABLED=0 go build -o bin/rdpgw cmd/rdpgw/main.go

#
# VPN
#
FROM alpine:3.22.0 as production
MAINTAINER isard <info@isardvdi.com>

RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories

RUN apk -U upgrade --no-cache

RUN apk add --no-cache \
    wireguard-tools \
    openssh \
    openvswitch@community=3.7.0-r1 \
    dnsmasq \
    # For WireGuard and others
    iptables \
    # For python-iptables
    iptables-legacy \
    # For guacd (RDP Web)
    guacamole-server@community \
    guacamole-server-dev@community \
    guacamole-server-rdp@community \
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
    rm requirements.txt
    # apk del .build_deps

# Required for python-iptables
ENV XTABLES_LIBDIR=/usr/lib/xtables
RUN ln -s /usr/sbin/iptables /sbin/iptables

COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /

COPY --from=rdpgw-build /build/rdpgw/bin/rdpgw /rdpgw

CMD [ "sh", "run.sh"]
