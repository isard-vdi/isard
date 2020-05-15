FROM alpine:3.11.6
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache \
    libvirt \
    libvirt-daemon \
    dbus \
    polkit \
    openssh
    
COPY hyper/docker/qemu/bin /usr/bin/
COPY hyper/docker/qemu/share /usr/share
RUN ln -s /usr/bin/qemu-system-x86_64 /usr/bin/qemu-kvm

# Libvirt configuration and certs
RUN echo -e "listen_tls = 0\n \
    listen_tcp = 1" >> /etc/libvirt/libvirtd.conf
RUN echo -e 'spice_listen = "0.0.0.0"\n \
    spice_tls = 1\n \
    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf

# Create the required directories
RUN mkdir -p /etc/pki/libvirt-spice /var/log/supervisor

COPY hyper/docker/run.sh /
RUN chmod +x run.sh

CMD [ "sleep", "9999999"]
