#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587
ARG GOLANG_RUN_IMAGE=alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

FROM ${GOLANG_BUILD_IMAGE} AS build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY . /build/guac

WORKDIR /build/guac

RUN CGO_ENABLED=0 go build -o bin/guac cmd/guac/guac.go


#
# Guac
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache

COPY --from=build /build/guac/bin/guac /guac

CMD [ "/guac" ]
USER nobody
