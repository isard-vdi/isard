FROM alpine:3.12.0 as build-qemu
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache git \
    # QEMU
    make \
    python3 \
    gcc \
    g++ \
    libc-dev \
    pkgconf \
    linux-headers \
    glib-dev glib-static \
    zlib-dev zlib-static \
    pixman-dev  \
    bash \
    # QXL
    spice-dev \
    # USB Network redirection
    libusb-dev \
    usbredir-dev \
    # ui/shader/
    # pulseaudio-dev \
    #alsa-lib-dev \
    perl

# Build QEMU
RUN git clone --depth 1 --branch v5.1.0 https://github.com/qemu/qemu && \
    cd qemu && \
    mkdir -p bin/debug/native && \
    cd bin/debug/native && \
    ../../../configure --target-list=x86_64-softmmu --enable-debug --disable-werror \
	--enable-spice &&\
    make -j8 install
#--audio-drv-list=alsa &&\

FROM alpine:3.12.0 as production
MAINTAINER isard <info@isardvdi.com>

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
    openssl
    

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
    usbredir
    #vde2-libs 
    #libpulse

COPY --from=build-qemu /usr/local/ /usr/local/
RUN ln -s /usr/local/bin/qemu-img /usr/bin/qemu-img

COPY docker/hypervisor/qemu-kvm /usr/libexec/qemu-kvm
COPY docker/hypervisor/qemu-kvm /usr/bin/qemu-kvm
RUN chmod a+x /usr/bin/qemu-kvm
RUN chmod a+x /usr/libexec/qemu-kvm

# SSH configuration
RUN echo "root:isard" |chpasswd
RUN sed -i \
    -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' \
    -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' \
    -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' \
    -e 's|[#]*UsePAM yes|UsePAM yes|g' \
    -e 's|[#]*\(HostKey \)\(/etc/ssh/.*\)$|\1/usr/local\2|' \
    /etc/ssh/sshd_config
    
# Libvirt configuration and certs
RUN useradd -ms /bin/sh qemu
COPY docker/hypervisor/50-libvirt.rules /etc/polkit-1/rules.d/50-libvirt.rules
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

RUN apk add py3-pip
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir rethinkdb==2.3.0.post6

COPY docker/hypervisor/checks/domain.xml /checks/
COPY docker/hypervisor/auto-generate-certs.sh /
COPY docker/hypervisor/vlans-add.sh /
COPY docker/hypervisor/vlans-discover.sh /
COPY docker/hypervisor/vlans-db.py /
RUN apk add bash
COPY docker/hypervisor/wireguard.sh /
COPY docker/hypervisor/wireguard.py /
COPY docker/hypervisor/update-client-ips.* /
RUN chmod 744 /update-client-ips.sh
COPY docker/hypervisor/api_client.py /
COPY docker/hypervisor/run.sh /
RUN chmod +x run.sh auto-generate-certs.sh

COPY docker/hypervisor/networks/ /etc/libvirt/qemu/networks/
#COPY docker/hypervisor/networks/ /etc/libvirt/qemu/networks/autostart/

CMD [ "sh", "run.sh"]
