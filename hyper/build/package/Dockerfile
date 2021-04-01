#
# Build phase
#
FROM golang:1.16-alpine as build

RUN apk add --no-cache \
    git \
    make \
    build-base \
    libvirt-dev \
    pkgconf

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY pkg /build/pkg
COPY hyper /build/hyper

WORKDIR /build/hyper

RUN make build


#
# Hyper
#
FROM alpine:3.13

RUN apk add --no-cache \
	qemu-system-x86_64 \
	libvirt \
	libvirt-daemon \
        openssl

RUN echo -e "listen_tls = 0\n \
    listen_tcp = 1" >> /etc/libvirt/libvirtd.conf

RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf

RUN mkdir -p /etc/pki/libvirt-spice

COPY --from=build /build/hyper/build/package/entrypoint.sh /entrypoint.sh
COPY --from=build /build/hyper/bin/hyper-v /hyper

CMD [ "/entrypoint.sh" ]
