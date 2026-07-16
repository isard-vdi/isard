#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587
ARG GOLANG_RUN_IMAGE=alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

FROM ${GOLANG_BUILD_IMAGE} as build

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
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache

COPY --from=build /build/orchestrator/bin/orchestrator /orchestrator

CMD [ "/orchestrator" ]
