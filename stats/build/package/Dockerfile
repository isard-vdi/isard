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

RUN apk add --no-cache \
    build-base \
    pkgconfig \
    libvirt-dev

COPY pkg /build/pkg
COPY stats /build/stats

WORKDIR /build/stats

RUN go build -o bin/stats cmd/stats/main.go


#
# Stats
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    ca-certificates \
    util-linux \
    openssh-client \
    sshpass \
    socat \
    pkgconfig \
    libvirt-dev

COPY --from=build /build/stats/bin/stats /stats
COPY --from=build /build/stats/build/package/run.sh /run.sh

CMD [ "/run.sh" ]
