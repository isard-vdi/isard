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
COPY sessions /build/sessions

WORKDIR /build/sessions

RUN CGO_ENABLED=0 go build -o bin/sessions cmd/sessions/main.go


#
# Sessions
#
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache

COPY --from=build /build/sessions/bin/sessions /sessions

CMD [ "/sessions" ]
