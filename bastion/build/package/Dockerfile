#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22@sha256:6b7607461f105ccaa0615b6f7932dfd5b36c5d827a0770b5578e565107cc3adb
ARG GOLANG_RUN_IMAGE=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce

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
