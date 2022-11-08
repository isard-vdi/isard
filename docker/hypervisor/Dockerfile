# Use debian ovmf
FROM debian:11-slim as ovmf

RUN apt-get update && apt-get install -y \
    ovmf && \
    rm -rf /var/lib/apt/lists/*

# Build mdevctl
FROM alpine:3.16 as build

RUN apk add --no-cache cargo uuidgen py3-docutils make git

RUN cd /opt && git clone https://github.com/mdevctl/mdevctl -b v1.2.0

WORKDIR /opt/mdevctl
RUN CARGO_INCREMENTAL=0 cargo build --release
RUN make install || true

# Image isard-hypervisor
FROM alpine:3.15 as production
MAINTAINER isard <info@isardvdi.com>

RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories

RUN apk add --no-cache \
    libvirt \
    libvirt-daemon \
    dbus \
    polkit \
    openssh \
    curl \
    rsync \
    ovmf \
    iproute2 \
    bridge-utils \
    shadow \
    tshark \
    openssl \
    qemu \
    qemu-img \
    qemu-modules \
    qemu-system-x86_64 \
    libcrypto3@edge \
    swtpm@community
    

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
    coreutils
    #vde2-libs 
    #libpulse

COPY docker/hypervisor/kvm/qemu-kvm /usr/libexec/qemu-kvm
COPY docker/hypervisor/kvm/qemu-kvm /usr/bin/qemu-kvm
RUN chmod a+x /usr/bin/qemu-kvm
RUN chmod a+x /usr/libexec/qemu-kvm
RUN ln -s /usr/bin/qemu-system-x86_64 /usr/local/bin/qemu-system-x86_64

RUN rm -rf /usr/share/OVMF
COPY --from=ovmf /usr/share/OVMF /usr/share/OVMF
COPY --from=ovmf /usr/share/ovmf/OVMF.fd /usr/share/OVMF

# SSH configuration
RUN echo "root:isard" |chpasswd
RUN sed -i \
    -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' \
    -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' \
    -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' \
    -e 's|[#]*UsePAM yes|UsePAM yes|g' \
    -e 's|[#]*Port 22|Port 2022|g' \
    /etc/ssh/sshd_config
    
# Libvirt configuration and certs
COPY docker/hypervisor/kvm/50-libvirt.rules /etc/polkit-1/rules.d/50-libvirt.rules
RUN sed -i "/^wheel:x:10:root/c\wheel:x:10:root,qemu" /etc/group
RUN sed -i "/^kvm:x:34:kvm/c\kvm:x:34:kvm,qemu" /etc/group
RUN echo -e 'listen_tls = 0\n \
    listen_tcp = 1\n \
    unix_sock_group = "kvm"' >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf

# Create the required directories
RUN mkdir -p /etc/pki/libvirt-spice
RUN mkdir /root/.ssh

# Add needed sources
COPY docker/hypervisor/networks/ /etc/libvirt/qemu/networks/

# Api
RUN apk add  --no-cache bash python3 py3-pip py3-requests
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev 
RUN pip3 install --no-cache-dir python-jose==3.3.0 python-iptables==1.0.0 pythonping==1.0.15
# RUN apk del .build_deps

# Openvswitch
RUN apk add openvswitch libxml2-utils
RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/

RUN apk add wireguard-tools

# FILESYSTEMS
## NFS client
RUN apk add --no-cache nfs-utils

## SEAWEEDFS
#RUN wget https://github.com/chrislusf/seaweedfs/releases/download/2.64/linux_amd64_large_disk.tar.gz
#RUN tar xvf linux_amd64_large_disk.tar.gz
#RUN rm linux_amd64_large_disk.tar.gz
#RUN mv weed /usr/local/bin/

## CIFS
RUN apk add --no-cache cifs-utils

## MDEVCTL
RUN mkdir -p \
    /etc/mdevctl.d \
    /usr/sbin \
    /etc/mdevctl.d/scripts.d/callouts \
    /etc/mdevctl.d/scripts.d/notifiers

COPY --from=build /usr/sbin/mdevctl /usr/sbin/mdevctl

# RUNTIME
COPY docker/hypervisor/src /src
COPY docker/hypervisor/kvm/hooks /etc/libvirt/hooks
WORKDIR /src
CMD [ "/src/start.sh"]

