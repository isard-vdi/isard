#
# Build phase
#
FROM golang:1.16-alpine as build

RUN apk add --no-cache \
    git \
    pkgconfig \
    libvirt-dev

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY stats /build/stats

WORKDIR /build/stats

RUN go build -o bin/stats cmd/stats/main.go


#
# Stats
#
FROM alpine

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
