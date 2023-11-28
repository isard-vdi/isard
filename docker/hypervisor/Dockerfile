FROM fedora:39 AS production

# Install base packages
RUN dnf update -y && \
    dnf install -y \
        # Virtualization
        bridge-utils \
        libvirt \
        qemu-kvm \
        openssh-server \
        mdevctl \
        edk2-ovmf \
        # Networking
        openvswitch \
        wireguard-tools \
        # Runtime
        python3 \
        python3-pip \
        python3-devel \
        gcc && \
    dnf clean all

# SSH configuration
RUN mkdir -p /root/.ssh
RUN echo "root:isard" |chpasswd
RUN sed -i \
    -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' \
    -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' \
    -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' \
    -e 's|[#]*UsePAM yes|UsePAM yes|g' \
    -e 's|[#]*Port 22|Port 2022|g' \
    /etc/ssh/sshd_config
    
# Libvirt configurations and certificates setup
RUN mkdir -p /etc/pki/libvirt-spice
COPY docker/hypervisor/kvm/hooks /etc/libvirt/hooks
COPY docker/hypervisor/kvm/50-libvirt.rules /etc/polkit-1/rules.d/50-libvirt.rules
RUN ln -s /usr/bin/qemu-system-x86_64 /usr/local/bin/qemu-system-x86_64
RUN sed -i "/^wheel:x:10:root/c\wheel:x:10:root,qemu" /etc/group
RUN sed -i "/^kvm:x:34:kvm/c\kvm:x:34:kvm,qemu" /etc/group
RUN echo -e 'listen_tls = 0\n \
    listen_tcp = 1\n \
    unix_sock_group = "kvm"' >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"\n \
    user = "root"\n \
    group = "root"' >> /etc/libvirt/qemu.conf

# Setup networking configuration
COPY docker/hypervisor/networks/ /etc/libvirt/qemu/networks/
RUN /usr/bin/ovsdb-tool create /etc/openvswitch/conf.db
RUN mkdir -pv /var/run/openvswitch/

# Install python runtime dependencies
COPY docker/hypervisor/requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

# Copy runtime code
COPY docker/hypervisor/src /src
COPY component/_common/src /src/_common

WORKDIR /src

ENV container docker

CMD [ "/src/start.sh"]
