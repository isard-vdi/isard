FROM fedora:34 as build
# Build filebrowser

#Set up environment
ENV GOPATH=/home/golang/ \
    GOOS=linux \ 
    GOARCH=amd64  

#Install golang
RUN dnf -y install --setopt=tsflags=nodocs golang npm && dnf clean all

RUN git clone https://github.com/filebrowser/filebrowser /filebrowser
RUN cd /filebrowser/frontend && npm install && npm run build
RUN cd /filebrowser && go mod download && go build

# PRODUCTION
FROM fedora:34 as production
MAINTAINER isard <info@isard.com>

# guestfs tools and libvirt
RUN dnf install -y libguestfs libguestfs-tools-c virt-v2v \
                   libvirt-daemon libvirt-daemon-config-network \
                   python3-pip python3-libvirt
RUN dnf clean all

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

COPY --from=build /filebrowser/filebrowser /filebrowser

# Api src needed
# RUN apk add  --no-cache bash python3 py3-pip py3-requests
RUN dnf install gcc -y
RUN pip3 install --upgrade pip
# RUN apk add --no-cache --virtual .build_deps \
#     build-base \
#     python3-dev \
#     libffi-dev 
RUN pip3 install --no-cache-dir python-jose==3.3.0 python-iptables==1.0.0 pythonping==1.0.15
# RUN apk del .build_deps
RUN dnf remove gcc -y

COPY docker/toolbox/src /src
COPY docker/toolbox/init.sh /init.sh

ENTRYPOINT [""]
CMD ["/bin/sh","/init.sh"]
