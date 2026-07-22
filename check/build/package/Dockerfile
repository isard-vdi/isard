#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22@sha256:6b7607461f105ccaa0615b6f7932dfd5b36c5d827a0770b5578e565107cc3adb
ARG GOLANG_RUN_IMAGE=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce

FROM ${GOLANG_BUILD_IMAGE} as build

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
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    bash \
    docker \
    jq

COPY --from=build /build/check/bin/check /check

CMD [ "/check" ]
