FROM alpine:3.9
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
    qemu-system-x86_64 \
    libvirt \
    netcat-openbsd \
    libvirt-daemon \
    dbus \
    polkit \
    qemu-img \
    openssh \
    curl \
    python3 \
    supervisor

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev 
RUN pip3 install --no-cache-dir websockify==0.8.0
RUN apk del .build_deps

RUN ln -s /usr/bin/qemu-system-x86_64 /usr/bin/qemu-kvm

# SSH configuration
RUN echo "root:isard" |chpasswd
RUN ssh-keygen -A
RUN sed -i \
    -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' \
    -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' \
    -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' \
    -e 's|[#]*UsePAM yes|UsePAM yes|g' /etc/ssh/sshd_config

# Libvirt configuration and certs
RUN echo -e "listen_tls = 0\n \
    listen_tcp = 1" >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf

# Create the required directories
RUN mkdir -p /etc/pki/libvirt-spice /var/log/supervisor

COPY dockers/hypervisor/reset-hyper.sh /
COPY dockers/hypervisor/start_proxy.py /
COPY dockers/hypervisor/supervisord.conf /etc/supervisord.conf

EXPOSE 5900-5950
EXPOSE 55900-55950

VOLUME [ "/isard" ]

CMD [ "/usr/bin/supervisord", "-c", "/etc/supervisord.conf" ]
