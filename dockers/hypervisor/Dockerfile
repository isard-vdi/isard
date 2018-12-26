FROM isard/alpine-pandas:1.0.0
MAINTAINER isard <info@isard.com>

RUN pip3 uninstall pandas pytz python-dateutil six -y

RUN apk --no-cache add qemu-system-x86_64 libvirt netcat-openbsd libvirt-daemon dbus polkit qemu-img
RUN ln -s /usr/bin/qemu-system-x86_64 /usr/bin/qemu-kvm
RUN apk add openssh curl bash
RUN ssh-keygen -A

RUN echo "root:isard" |chpasswd
RUN sed -i 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' /etc/ssh/sshd_config
RUN sed -i 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' /etc/ssh/sshd_config
RUN sed -i 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' /etc/ssh/sshd_config
RUN sed -i 's|[#]*UsePAM yes|UsePAM yes|g' /etc/ssh/sshd_config

RUN echo "listen_tls = 0" >> /etc/libvirt/libvirtd.conf; 
RUN echo 'listen_tcp = 1' >> /etc/libvirt/libvirtd.conf;

# libvirt configuration and certs
RUN echo 'spice_listen = "0.0.0.0"' >> /etc/libvirt/qemu.conf && \
echo 'spice_tls = 1' >> /etc/libvirt/qemu.conf && \
echo 'spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"' >> /etc/libvirt/qemu.conf
RUN mkdir -p /etc/pki/libvirt-spice

RUN apk add --no-cache --virtual .build_deps build-base python3-dev 
RUN pip3 install --no-cache-dir websockify==0.8.0
RUN apk del .build_deps
ADD dockers/hypervisor/start_proxy.py /

EXPOSE 22
EXPOSE 5900-5950
EXPOSE 55900-55950

VOLUME ["/isard" ]

RUN apk add --no-cache supervisor
RUN mkdir -p /var/log/supervisor
COPY dockers/hypervisor/supervisord.conf /etc/supervisord.conf
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]



