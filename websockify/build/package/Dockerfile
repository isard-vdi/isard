#
# Build phase
#
ARG GOLANG_BUILD_IMAGE=golang:1.25.8-alpine3.22
ARG GOLANG_RUN_IMAGE=alpine:3.22.0

FROM ${GOLANG_BUILD_IMAGE} as build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY websockify /build/websockify

WORKDIR /build/websockify

RUN CGO_ENABLED=0 go build -o bin/websockify cmd/websockify/main.go


#
# Websockify
# 
FROM ${GOLANG_RUN_IMAGE}

RUN apk -U upgrade --no-cache

COPY --from=build /build/websockify/bin/websockify /websockify

USER nobody

CMD [ "/websockify" ]
