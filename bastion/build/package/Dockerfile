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
COPY bastion /build/bastion

WORKDIR /build/bastion

RUN CGO_ENABLED=0 go build -o bin/bastion cmd/bastion/main.go


#
# Bastion
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    openvswitch

RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/

COPY --from=build /build/bastion/build/package/run.sh /run.sh
COPY --from=build /build/bastion/bin/bastion /bastion

CMD [ "/run.sh" ]
