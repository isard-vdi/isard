FROM golang:1.14-alpine as build

RUN apk add --no-cache \
	make

COPY . /go/src/github.com/isard-vdi/isard/hyper-stats
WORKDIR /go/src/github.com/isard-vdi/isard/hyper-stats

RUN make build

FROM alpine:3.11
MAINTAINER isard <info@isard.com>

COPY --from=build /go/src/github.com/isard-vdi/isard/hyper-stats/hyper-stats /

EXPOSE 8080

CMD [ "/hyper-stats" ]
