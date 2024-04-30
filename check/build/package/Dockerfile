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
