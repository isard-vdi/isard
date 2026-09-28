# syntax=docker/dockerfile:1.20

ARG GOLANG_BUILD_IMAGE=golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587

FROM ${GOLANG_BUILD_IMAGE} AS rdpgw-build
WORKDIR /build
COPY go.mod /build
COPY go.sum /build
RUN go mod download
WORKDIR /
COPY pkg /build/pkg
COPY rdpgw /build/rdpgw
WORKDIR /build/rdpgw
RUN CGO_ENABLED=0 go build -o bin/rdpgw cmd/rdpgw/main.go

FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache \
    autoconf automake build-base git libffi-dev libtool linux-headers \
    musl-dev openssl-dev python3-dev

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-vpn --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-vpn --no-editable

# RDP plugin with the GUACAMOLE-2221 busy-loop fix; drop once Alpine ships guacamole-server 1.6.1
FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS guacd-rdp-build
ARG GUACAMOLE_SERVER_VERSION=1.6.0
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories
RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    build-base cairo-dev freerdp2-dev@community libjpeg-turbo-dev libpng-dev \
    libssh2-dev libwebp-dev openssl-dev ossp-uuid-dev pango-dev perl
ADD --checksum=sha256:8bc45675da96d7b6f39728160181e3d4ff3c08f460f6d26de5805b642bf13f2b \
    https://archive.apache.org/dist/guacamole/${GUACAMOLE_SERVER_VERSION}/source/guacamole-server-${GUACAMOLE_SERVER_VERSION}.tar.gz /build/
COPY docker/vpn/guacd-patches /build/patches
WORKDIR /build
RUN tar xzf guacamole-server-${GUACAMOLE_SERVER_VERSION}.tar.gz
WORKDIR /build/guacamole-server-${GUACAMOLE_SERVER_VERSION}
RUN for p in /build/patches/*.patch; do patch -p1 < "$p"; done
RUN CFLAGS="-Wno-error" ./configure --prefix=/usr --sysconfdir=/etc --localstatedir=/var \
    --disable-static --with-ssl --with-pango --with-terminal --with-rdp --with-ssh --with-webp \
    --without-vnc --without-telnet --without-websockets --without-winsock
RUN make -j"$(nproc)"

FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS runtime
RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories
RUN apk -U upgrade --no-cache
# @community (edge) is load-bearing here: Alpine stable also ships guacamole, so dropping
# it silently downgrades guacd 1.6 -> 1.5.5 and breaks RDP Browser against the 1.6 client.
RUN apk add --no-cache \
    conntrack-tools dnsmasq guacamole-server@community \
    guacamole-server-dev@community guacamole-server-rdp@community \
    iptables libffi openssh openssl \
    openvswitch wireguard-tools

RUN apk info -v | grep -qx 'guacamole-server-rdp-1\.6\.0-r[0-9]*' \
    || { echo "guacamole-server-rdp is no longer 1.6.0: re-check GUACAMOLE-2221" >&2; exit 1; }
COPY --from=guacd-rdp-build /build/guacamole-server-1.6.0/src/protocols/rdp/.libs/libguac-client-rdp.so.0.0.0 /usr/lib/

# The host AppArmor profile attaches to /usr/bin/wg-quick and Docker does not
# namespace AppArmor, so we call a copy the profile does not match.
RUN install -D /usr/bin/wg-quick /isard/bin/wg-quick

RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/
COPY docker/vpn/ovs /ovs

ENV XTABLES_LIBDIR=/usr/lib/xtables
RUN ln -s /usr/sbin/iptables /sbin/iptables

COPY --from=builder /.venv /.venv
COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/run.sh /
COPY --from=rdpgw-build /build/rdpgw/bin/rdpgw /rdpgw
ENV PATH="/.venv/bin:$PATH"
WORKDIR /
CMD ["sh", "run.sh"]
