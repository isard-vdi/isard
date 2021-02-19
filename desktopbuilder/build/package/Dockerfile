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
COPY desktopbuilder /build/desktopbuilder


WORKDIR /build/desktopbuilder

RUN make build


#
# DesktopBuilder
#
FROM alpine:3.12

COPY --from=build /build/desktopbuilder/bin/desktopbuilder-v /desktopbuilder

CMD [ "/desktopbuilder" ]