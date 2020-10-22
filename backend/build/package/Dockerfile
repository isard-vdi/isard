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

COPY . /build

WORKDIR /build/backend

RUN make build


#
# Backend
#
FROM alpine:3.12

COPY --from=build /build/backend/bin/backend-v /backend

CMD [ "/backend" ]
