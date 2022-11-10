#
# Build phase
#
FROM golang:1.19-alpine as build

RUN apk add --no-cache \
    git

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY orchestrator /build/orchestrator

WORKDIR /build/orchestrator

RUN CGO_ENABLED=0 go build -o bin/orchestrator cmd/orchestrator/main.go


#
# Orchestrator
#
FROM alpine:3.16

COPY --from=build /build/orchestrator/bin/orchestrator /orchestrator

CMD [ "/orchestrator" ]
