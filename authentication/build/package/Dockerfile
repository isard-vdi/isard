#
# Build phase
#
ARG GOLANG_BUILD_IMAGE
ARG GOLANG_RUN_IMAGE

FROM ${GOLANG_BUILD_IMAGE} as build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

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
    openssl

COPY --from=build /build/authentication/build/package/run.sh /run.sh
COPY --from=build /build/authentication/bin/authentication /authentication

CMD [ "/run.sh" ]
