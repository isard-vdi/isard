ARG HAPROXY_RUN_IMAGE
ARG GOLANG_BUILD_IMAGE=golang:1.26.10-alpine3.24@sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca

# Build haproxy-sync binary
FROM ${GOLANG_BUILD_IMAGE} as haproxy-sync-build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY haproxy-sync /build/haproxy-sync

WORKDIR /build/haproxy-sync

RUN CGO_ENABLED=0 go build -o bin/haproxy-sync cmd/haproxy-sync/main.go
RUN CGO_ENABLED=0 go build -o bin/cert-watch cmd/cert-watch/main.go

# HAProxy production image
FROM ${HAPROXY_RUN_IMAGE} as production

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache openssl acme.sh

# Copy haproxy-sync binary
COPY --from=haproxy-sync-build /build/haproxy-sync/bin/haproxy-sync /usr/local/bin/haproxy-sync
COPY --from=haproxy-sync-build /build/haproxy-sync/bin/cert-watch /usr/local/bin/cert-watch

# Copy HAProxy scripts and configs
COPY docker/haproxy/_common/prepare.sh /usr/local/sbin/
COPY docker/haproxy/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/haproxy/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/haproxy/_common/haproxy-healthy /usr/local/bin/haproxy-healthy
COPY docker/haproxy/_common/haproxy-watchdog /usr/local/bin/haproxy-watchdog
COPY docker/haproxy/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/haproxy/_common/acme-management.sh /usr/local/bin/acme-management.sh
COPY docker/haproxy/_common/acme-generate-cert.sh /usr/local/bin/acme-generate-cert.sh
COPY docker/haproxy/_common/acme-cron.sh /usr/local/bin/acme-cron.sh
COPY docker/haproxy/_common/acme-remove-cert.sh /usr/local/bin/acme-remove-cert.sh

RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 \
    /docker-entrypoint.sh \
    /usr/local/sbin/prepare.sh \
    /usr/local/sbin/auto-generate-certs.sh \
    /usr/local/bin/haproxy-reload \
    /usr/local/bin/acme-management.sh \
    /usr/local/bin/acme-generate-cert.sh \
    /usr/local/bin/acme-cron.sh \
    /usr/local/bin/acme-remove-cert.sh \
    /usr/local/bin/haproxy-sync

COPY docker/haproxy/cfg /usr/local/etc/haproxy/cfg
WORKDIR /usr/local/etc/haproxy
