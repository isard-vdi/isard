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