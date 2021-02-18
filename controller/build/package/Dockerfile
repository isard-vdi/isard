#
# Build phase
#
FROM golang:1.15-alpine as build

RUN apk add --no-cache \
    git \
    make

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY controller /build/controller

WORKDIR /build/controller

RUN make build


#
# Orchestrator
#
FROM alpine:3.12

COPY --from=build /build/controller/bin/controller-v /controller

CMD [ "/controller" ]