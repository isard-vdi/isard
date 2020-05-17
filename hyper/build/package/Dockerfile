FROM golang:1.14-alpine as build-go

RUN apk add --no-cache \
	make

COPY . /go/src/github.com/isard-vdi/isard/hyper
WORKDIR /go/src/github.com/isard-vdi/isard/hyper

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

RUN apk add --no-cache \
    libvirt \
    libvirt-daemon \
    dbus \
    polkit \
    openssh

RUN apk add --no-cache \
	libcap \
	mesa \
	libpciaccess \
	libdrm \
	wayland-libs-server \
	mesa-gbm \
	pixman \
	libxau \
	libxdmcp \
	libxcb \
	libx11 \
	libepoxy \
	virglrenderer \
	libxkbcommon \
	augeas-libs \
	libgpg-error \
	libgcrypt \
	libxslt \
	netcf-libs \
	libpcap \
	eudev-libs \
	libvirt-common-drivers \
	libvirt-qemu \
	libjpeg-turbo \
	lzo \
	libpng \
	libseccomp \
	snappy \
	mesa-glapi \
	wayland-libs-client \
	libxshmfence \
	mesa-egl \
	libxdamage \
	libxext \
	libxfixes \
	libxxf86vm \
	mesa-gl \
	libxv \
	alsa-lib \
	libxrender \
	libbz2 \
	freetype \
	fontconfig \
	cairo \
	cdparanoia-libs \
	gstreamer \
	libogg \
	opus \
	orc \
	libxft \
	fribidi \
	graphite2 \
	harfbuzz \
	pango \
	libtheora \
	libvorbis \
	wayland-libs-egl \
	gst-plugins-base \
	lz4-libs \
	spice-server \
	libusb \
	usbredir \
	vde2-libs

COPY --from=build-go /go/src/github.com/isard-vdi/isard/hyper/hyper /
COPY --from=build-qemu /usr/local/ /usr/local/
RUN ln -s /usr/local/bin/qemu-system-x86_64 /usr/libexec/qemu-kvm

# Libvirt configuration and certs
RUN echo -e "listen_tls = 0\n \
    listen_tcp = 1" >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf

# Create the required directories
RUN mkdir -p /etc/pki/libvirt-spice

COPY build/package/checks/domain.xml /checks/
COPY build/package/auto-generate-certs.sh /
COPY build/package/run.sh /
RUN chmod +x run.sh auto-generate-certs.sh

CMD [ "sh", "run.sh"]
