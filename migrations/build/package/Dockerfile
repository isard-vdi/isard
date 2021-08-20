#
# Build phase
#
FROM golang:1.16-alpine as build

RUN apk add --no-cache \
    git \
    make \
    build-base \
    libvirt-dev \
    pkgconf

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY migrations /build/migrations

WORKDIR /build/migrations

RUN make build

#
# Hyper
#
FROM scratch

COPY --from=build /build/migrations/bin/migrations-v /migrations

CMD [ "/migrations" ]
