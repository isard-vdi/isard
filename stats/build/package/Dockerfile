#
# Build phase
#
ARG GOLANG_BUILD_IMAGE
ARG GOLANG_RUN_IMAGE

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

# TODO: Remove this after Go 1.22
RUN GOEXPERIMENT=loopvar go build -o bin/stats cmd/stats/main.go


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
