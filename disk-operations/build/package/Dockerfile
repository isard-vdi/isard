FROM golang:1.14-alpine as build-go

RUN apk add --no-cache \
	make

COPY . /go/src/github.com/isard-vdi/isard/disk-operations
WORKDIR /go/src/github.com/isard-vdi/isard/disk-operations

RUN make build

FROM alpine:3.11
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache \
    libvirt \
    libvirt-daemon \
    dbus \
    polkit \
    openssh

COPY --from=build-go /go/src/github.com/isard-vdi/isard/disk-operations /

COPY build/package/run.sh /

CMD [ "sh", "run.sh"]
