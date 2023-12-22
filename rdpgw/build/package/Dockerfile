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
COPY rdpgw /build/rdpgw

WORKDIR /build/rdpgw

RUN CGO_ENABLED=0 go build -o bin/rdpgw cmd/rdpgw/main.go

#
# RDP Gateway
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    ca-certificates

COPY --from=build /build/rdpgw/bin/rdpgw /rdpgw

CMD [ "/rdpgw" ]
USER nobody