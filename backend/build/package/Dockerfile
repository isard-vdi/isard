FROM golang:1.14-alpine as build

RUN apk add --no-cache \
	make

COPY . /go/src/github.com/isard-vdi/isard/backend
WORKDIR /go/src/github.com/isard-vdi/isard/backend

RUN make build

FROM alpine:3.11.3
MAINTAINER isard <info@isard.com>

COPY --from=build /go/src/github.com/isard-vdi/isard/backend /

EXPOSE 8080

CMD [ "/backend" ]
