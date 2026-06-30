ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22

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

FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache \
    autoconf automake build-base git libffi-dev libtool linux-headers \
    musl-dev openssl-dev python3-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-vpn --no-editable

FROM python:3.13-alpine AS runtime
RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories
RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    conntrack-tools dnsmasq guacamole-server guacamole-server-dev \
    guacamole-server-rdp iptables libffi openssh openssl \
    openvswitch@community wireguard-tools

RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/
COPY docker/vpn/ovs /ovs

ENV XTABLES_LIBDIR=/usr/lib/xtables
RUN ln -s /usr/sbin/iptables /sbin/iptables

COPY --from=builder /.venv /.venv
COPY docker/vpn/dnsmasq-hook /dnsmasq-hook
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /
COPY --from=rdpgw-build /build/rdpgw/bin/rdpgw /rdpgw
ENV PATH="/.venv/bin:$PATH"
WORKDIR /
CMD ["sh", "run.sh"]
