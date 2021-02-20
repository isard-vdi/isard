FROM fedora:latest as production
MAINTAINER isard <info@isard.com>

RUN dnf install -y libguestfs libguestfs-tools-c virt-v2v \
                   libvirt-daemon libvirt-daemon-config-network \
                   python3-pip python3-libvirt

RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir requests xmltodict ipython rethinkdb==2.3.0.post6

# https://bugzilla.redhat.com/show_bug.cgi?id=1045069
RUN useradd -ms /bin/bash v2v
#USER v2v
#WORKDIR /home/v2v

# This is required for virt-v2v because neither systemd nor
# root libvirtd runs, and therefore there is no virbr0, and
# therefore virt-v2v cannot set up the network through libvirt.
ENV LIBGUESTFS_BACKEND direct

CMD ["/usr/bin/sleep","100000"]
