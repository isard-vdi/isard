FROM fedora:42 as production
MAINTAINER isard <info@isard.com>

COPY docker/storage/requirements.txt /requirements.txt

RUN dnf update -y \
    && dnf install -y libguestfs libguestfs-tools-c virt-v2v \
        libvirt-daemon libvirt-daemon-config-network \
        python3-pip python3-libvirt python3-libguestfs \
        git autoconf automake pkg-config gettext-devel libtool python3-devel gcc rsync \
        virt-install python3-cachetools virt-win-reg

RUN pip3 install --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt

RUN dnf remove -y git autoconf automake pkg-config gettext-devel libtool python3-devel gcc \
    && dnf clean all \
    && dnf autoremove -y \
    && rm -rf /var/cache/yum


# This is required for virt-v2v because neither systemd nor
# root libvirtd runs, and therefore there is no virbr0, and
# therefore virt-v2v cannot set up the network through libvirt.
ENV LIBGUESTFS_BACKEND direct

# https://bugzilla.redhat.com/show_bug.cgi?id=1045069
RUN useradd -ms /bin/bash v2v
#USER v2v
#WORKDIR /home/v2v

ENV PYTHONPATH /opt/isardvdi
COPY pkg/gen/proto/python_old /opt/isardvdi/isardvdi_protobuf_old
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY docker/storage/task /opt/isardvdi/isardvdi_task
COPY docker/storage/init.sh /init.sh
COPY docker/storage/utils /usr/local/sbin
CMD ["/init.sh"]