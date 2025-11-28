# Stage 1: Build Go microservice
ARG GOLANG_BUILD_IMAGE
ARG HAPROXY_RUN_IMAGE

FROM ${GOLANG_BUILD_IMAGE} as gobuilder

WORKDIR /build

# Copy go dependencies
RUN mkdir -p /build/pkg/sdk
COPY go.mod /build
COPY go.sum /build
COPY pkg/sdk/go.mod /build/pkg/sdk
COPY pkg/sdk/go.sum /build/pkg/sdk

RUN go mod download

# Copy source
COPY pkg /build/pkg

WORKDIR /build/pkg/haproxy-bastion-sync

# Generate go.sum and download dependencies
RUN go mod tidy

# Build binary
RUN CGO_ENABLED=0 go build -o bin/haproxy-bastion-sync cmd/haproxy-bastion-sync/main.go

# Stage 2: HAProxy runtime
FROM ${HAPROXY_RUN_IMAGE} as production

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache openssl acme.sh

# Copy haproxy-bastion-sync binary from builder stage
COPY --from=gobuilder /build/pkg/haproxy-bastion-sync/bin/haproxy-bastion-sync /usr/local/bin/haproxy-bastion-sync

# Copy HAProxy scripts and configs
COPY docker/haproxy/_common/prepare.sh /usr/local/sbin/
COPY docker/haproxy/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/haproxy/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/haproxy/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/haproxy/_common/acme-management.sh /usr/local/bin/acme-management.sh

RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 \
    /docker-entrypoint.sh \
    /usr/local/sbin/prepare.sh \
    /usr/local/sbin/auto-generate-certs.sh \
    /usr/local/bin/haproxy-reload \
    /usr/local/bin/acme-management.sh \
    /usr/local/bin/haproxy-bastion-sync

COPY docker/haproxy/cfg /usr/local/etc/haproxy/cfg
WORKDIR /usr/local/etc/haproxy
