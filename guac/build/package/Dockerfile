#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22@sha256:6b7607461f105ccaa0615b6f7932dfd5b36c5d827a0770b5578e565107cc3adb
ARG GOLANG_RUN_IMAGE=alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce

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
