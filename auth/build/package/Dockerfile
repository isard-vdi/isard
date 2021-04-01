#
# Build phase
#
FROM golang:1.16-alpine as build

RUN apk add --no-cache \
    git \
    make

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY auth /build/auth

WORKDIR /build/auth

RUN make build


#
# Auth
#
FROM alpine:3.13

COPY --from=build /build/auth/bin/auth-v /auth

CMD [ "/auth" ]

