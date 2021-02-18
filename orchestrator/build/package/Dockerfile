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
COPY orchestrator /build/orchestrator

WORKDIR /build/orchestrator

RUN make build


#
# Orchestrator
#
FROM alpine:3.12

COPY --from=build /build/orchestrator/bin/orchestrator-v /orchestrator

CMD [ "/orchestrator" ]