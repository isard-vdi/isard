FROM golang:1.14-alpine as build-go

RUN apk add --no-cache \
	make \
    git

WORKDIR /go/src/github.com/isard-vdi/isard
COPY ./go.mod ./go.sum /go/src/github.com/isard-vdi/isard/
RUN go mod download

COPY . /go/src/github.com/isard-vdi/isard
WORKDIR /go/src/github.com/isard-vdi/isard/disk-operations

RUN make build

FROM alpine:3.11 as build-qemu
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache git \
	# QEMU
	make \
	python3 \
	gcc \
	libc-dev \
	pkgconf \
	linux-headers \
	glib-dev glib-static \
	zlib-dev zlib-static \
	pixman-dev  \
	# QXL
	spice-dev

# Build QEMU
RUN git clone git://git.qemu-project.org/qemu.git && \
	cd qemu && \
	mkdir -p bin/debug/native && \
	cd bin/debug/native && \
	../../../configure --target-list=x86_64-softmmu --enable-debug --disable-werror --enable-spice && \
	make -j8 install

FROM alpine:3.11
MAINTAINER isard <info@isardvdi.com>

COPY --from=build-go /go/src/github.com/isard-vdi/isard/disk-operations/disk-operations-bin /disk-operations
COPY --from=build-qemu /usr/local/ /usr/local/
RUN ln -s /usr/local/bin/qemu-system-x86_64 /usr/libexec/qemu-kvm

EXPOSE 1312

CMD [ "/disk-operations" ]
