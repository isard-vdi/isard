#
# Build phase
#
FROM golang:1.20-alpine AS build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY check /build/check

WORKDIR /build/check

RUN CGO_ENABLED=0 go build -o bin/check cmd/check/main.go

#
# Check
#
FROM alpine:3.18

RUN apk add --no-cache \
    bash \
    docker \
    jq

COPY --from=build /build/check/bin/check /check

CMD [ "/check" ]
