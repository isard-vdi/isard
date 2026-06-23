FROM debian:12-slim AS ovmf
RUN apt-get update && apt-get install -y ovmf && rm -rf /var/lib/apt/lists/*

FROM alpine:3.22 AS mdevctl-build
RUN apk add --no-cache cargo git make py3-docutils uuidgen
RUN cd /opt && git clone https://github.com/mdevctl/mdevctl -b v1.2.0
WORKDIR /opt/mdevctl
RUN CARGO_INCREMENTAL=0 cargo build --release
RUN make install || true

FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base cargo git libffi-dev make musl-dev openssl-dev py3-docutils python3-dev uuidgen

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-hypervisor --no-editable

# Pin runtime to alpine 3.22 — alpine 3.23 ships qemu 10.1.3 which is
# linked against libspice-server.so.1.15.0 (exports
# spice_qxl_gl_scanout2). The custom spice-dev override below ships
# 1.14.3 (no spice_qxl_gl_scanout2) → qemu fails to load the spice
# module → "domain configuration does not support video model 'qxl'".
# 3.22's qemu (9.2.x) is built against the older spice that the
# custom override matches.
FROM python:3.13-alpine3.22 AS runtime

RUN echo "@edge http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories
RUN echo "@testing http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN echo "@community http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories

RUN apk -U upgrade --no-cache

RUN mkdir -p /lib64 && \
    ln -sf /lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2

# eudev provides the `udevadm` CLI (eudev-libs alone does not). GPU discovery's
# SR-IOV VF cycle settles the kernel with `udevadm settle` after
# `sriov-manage -e` so the new VFs rebind to nvidia before mdev enumeration.
# Without it the settle is skipped and slower cards (e.g. A16 with many VFs)
# time out the VF-bound poll and fall back to a disruptive per-card
# `nvidia-smi -r` bus reset.
RUN apk add --no-cache \
    alsa-lib augeas-libs bash bridge-utils cairo cdparanoia-libs coreutils curl \
    dbus eudev eudev-libs fontconfig freetype fribidi gcompat graphite2 gst-plugins-base \
    gstreamer harfbuzz iproute2 libcap libcrypto3 libdrm libepoxy libffi libgcrypt \
    libgpg-error libjpeg-turbo libogg libpcap libpciaccess libpng libseccomp \
    libtheora libusb libvirt libvirt-common-drivers libvirt-daemon libvirt-qemu \
    libvorbis libx11 libxau libxcb libxdamage libxdmcp libxext libxfixes libxft \
    libxkbcommon libxml2-utils libxrender libxshmfence libxslt libxv libxxf86vm \
    lz4-libs lzo mesa mesa-egl mesa-gbm mesa-gl netcf-libs openssh openssl \
    openvswitch@community opus orc ovmf pango pciutils pixman polkit qemu \
    qemu-img qemu-modules qemu-system-x86_64 rsync shadow snappy speedtest-cli \
    spice-server swtpm tshark usbredir virglrenderer virtiofsd \
    wayland-libs-client wayland-libs-egl wayland-libs-server wireguard-tools

RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/

COPY docker/hypervisor/kvm/qemu-kvm /usr/libexec/qemu-kvm
COPY docker/hypervisor/kvm/qemu-kvm /usr/bin/qemu-kvm
RUN chmod a+x /usr/bin/qemu-kvm
RUN chmod a+x /usr/libexec/qemu-kvm
RUN ln -s /usr/bin/qemu-system-x86_64 /usr/local/bin/qemu-system-x86_64

RUN rm -rf /usr/share/OVMF
COPY --from=ovmf /usr/share/OVMF /usr/share/OVMF
COPY --from=ovmf /usr/share/ovmf/OVMF.fd /usr/share/OVMF

RUN echo "root:isard" |chpasswd
RUN sed -i \
    -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' \
    -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' \
    -e 's|[#]*#PubkeyAuthentication yes|PubkeyAuthentication yes|g' \
    -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' \
    -e 's|[#]*UsePAM yes|UsePAM yes|g' \
    -e 's|[#]*Port 22|Port 2022|g' \
    /etc/ssh/sshd_config

COPY docker/hypervisor/kvm/50-libvirt.rules /etc/polkit-1/rules.d/50-libvirt.rules
RUN sed -i "/^wheel:x:10:root/c\wheel:x:10:root,qemu" /etc/group
RUN sed -i "/^kvm:x:34:kvm/c\kvm:x:34:kvm,qemu" /etc/group
RUN echo -e 'listen_tls = 0\n \
    listen_tcp = 1\n \
    unix_sock_group = "kvm"' >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"\n \
    remember_owner = 0\n \
    dynamic_ownership = 0' >> /etc/libvirt/qemu.conf

RUN mkdir -p /etc/pki/libvirt-spice
RUN mkdir /root/.ssh

COPY docker/hypervisor/networks/ /opt/default_networks

RUN mkdir -p \
    /etc/mdevctl.d \
    /usr/sbin \
    /etc/mdevctl.d/scripts.d/callouts \
    /etc/mdevctl.d/scripts.d/notifiers
COPY --from=mdevctl-build /usr/sbin/mdevctl /usr/sbin/mdevctl

COPY --from=builder /.venv /.venv
COPY docker/hypervisor/src /src
COPY component/_common/src/isardvdi_common /src/isardvdi_common
COPY docker/hypervisor/kvm/hooks /etc/libvirt/hooks

RUN rm /usr/lib/libspice*
COPY docker/hypervisor/spice-dev/* /usr/lib/

ENV PATH="/.venv/bin:$PATH"
ENV G_MESSAGES_DEBUG=all
WORKDIR /src
CMD ["/src/start.sh"]
