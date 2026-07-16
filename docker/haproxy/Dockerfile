ARG HAPROXY_RUN_IMAGE
ARG GOLANG_BUILD_IMAGE=golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587

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

# HAProxy production image
FROM ${HAPROXY_RUN_IMAGE} as production

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache openssl acme.sh

# Copy haproxy-sync binary
COPY --from=haproxy-sync-build /build/haproxy-sync/bin/haproxy-sync /usr/local/bin/haproxy-sync

# Copy HAProxy scripts and configs
COPY docker/haproxy/_common/prepare.sh /usr/local/sbin/
COPY docker/haproxy/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/haproxy/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/haproxy/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/haproxy/_common/acme-management.sh /usr/local/bin/acme-management.sh
COPY docker/haproxy/_common/acme-generate-cert.sh /usr/local/bin/acme-generate-cert.sh
COPY docker/haproxy/_common/acme-remove-cert.sh /usr/local/bin/acme-remove-cert.sh

RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 \
    /docker-entrypoint.sh \
    /usr/local/sbin/prepare.sh \
    /usr/local/sbin/auto-generate-certs.sh \
    /usr/local/bin/haproxy-reload \
    /usr/local/bin/acme-management.sh \
    /usr/local/bin/acme-generate-cert.sh \
    /usr/local/bin/acme-remove-cert.sh \
    /usr/local/bin/haproxy-sync

COPY docker/haproxy/cfg /usr/local/etc/haproxy/cfg
WORKDIR /usr/local/etc/haproxy
