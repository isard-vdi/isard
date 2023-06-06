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
COPY orchestrator /build/orchestrator

WORKDIR /build/orchestrator

RUN CGO_ENABLED=0 go build -o bin/orchestrator cmd/orchestrator/main.go


#
# Orchestrator
#
FROM ${GOLANG_RUN_IMAGE}

COPY --from=build /build/orchestrator/bin/orchestrator /orchestrator

CMD [ "/orchestrator" ]
