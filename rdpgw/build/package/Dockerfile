#
# Build phase
#
FROM golang:1.17-alpine as build

RUN apk add --no-cache \
    git

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY rdpgw /build/rdpgw

WORKDIR /build/rdpgw

RUN CGO_ENABLED=0 go build -o bin/rdpgw cmd/rdpgw/main.go

#
# RDP Gateway
#
FROM alpine

RUN apk add --no-cache \
    ca-certificates

COPY --from=build /build/rdpgw/bin/rdpgw /rdpgw

CMD [ "/rdpgw" ]
