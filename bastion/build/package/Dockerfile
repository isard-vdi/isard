#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587
ARG GOLANG_RUN_IMAGE=alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

FROM ${GOLANG_BUILD_IMAGE} as build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY bastion /build/bastion

WORKDIR /build/bastion

RUN CGO_ENABLED=0 go build -o bin/bastion cmd/bastion/main.go


#
# Bastion
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories
RUN apk add --no-cache \
    openvswitch@community

RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/

COPY --from=build /build/bastion/build/package/run.sh /run.sh
COPY --from=build /build/bastion/bin/bastion /bastion

CMD [ "/run.sh" ]
