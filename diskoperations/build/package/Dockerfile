#
# Build phase
#
FROM golang:1.16-alpine as build

RUN apk add --no-cache \
    git \
    make
    # build-base

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY diskoperations /build/diskoperations

WORKDIR /build/diskoperations

RUN make build


#
# Disk Operations
#
FROM alpine:3.13

RUN apk add --no-cache \
    qemu-img

COPY --from=build /build/diskoperations/bin/diskoperations-v /diskoperations

CMD [ "/diskoperations" ]
