#
# Build phase
#
ARG GOLANG_BUILD_IMAGE
ARG GOLANG_RUN_IMAGE

FROM ${GOLANG_BUILD_IMAGE} as build

WORKDIR /build

RUN mkdir -p /build/pkg/sdk

COPY go.mod /build
COPY go.sum /build
COPY pkg/sdk/go.mod /build/pkg/sdk
COPY pkg/sdk/go.sum /build/pkg/sdk

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY authentication /build/authentication

WORKDIR /build/authentication

RUN CGO_ENABLED=0 go build -o bin/authentication cmd/authentication/main.go


#
# Authentication
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    ca-certificates \
    openssl \
    # Used for the healthcheck
    curl

COPY --from=build /build/authentication/build/package/run.sh /run.sh
COPY --from=build /build/authentication/bin/authentication /authentication

CMD [ "/run.sh" ]
