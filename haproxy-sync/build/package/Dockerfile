#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22
ARG GOLANG_RUN_IMAGE=alpine:3.22

FROM ${GOLANG_BUILD_IMAGE} as build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY haproxy-sync /build/haproxy-sync

WORKDIR /build/haproxy-sync

RUN CGO_ENABLED=0 go build -o bin/haproxy-sync cmd/haproxy-sync/main.go

#
# HAProxy Bastion sync
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    ca-certificates

COPY --from=build /build/haproxy-sync/bin/haproxy-sync /haproxy-sync

CMD [ "/haproxy-sync" ]
USER nobody
