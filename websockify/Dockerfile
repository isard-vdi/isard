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

COPY . /build

RUN go build -o websockify main.go


#
# Websockify
# 
FROM ${GOLANG_RUN_IMAGE}

MAINTAINER isard <info@isardvdi.com>

RUN apk -U upgrade --no-cache

COPY --from=build /build/websockify /

CMD [ "/websockify" ]
