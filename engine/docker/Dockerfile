FROM alpine:3.20 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    py3-libvirt \
    py3-paramiko \
    py3-openssl \
    py3-bcrypt \
    py3-flask \
    py3-pip \
    openssh-client \
    libvirt-client \
    curl \
    sshpass \
    pciutils-libs \
    hwids-pci

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    libc-dev \
    libxml2-dev \
    libxslt-dev \
    gcc

RUN apk upgrade openssh-client
RUN pip3 install --upgrade pip --break-system-package
COPY engine/docker/requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt  --break-system-package
RUN apk del .build_deps

RUN apk add --no-cache openssl shadow
RUN useradd -u 1000 -ms /bin/sh qemu
# Copy the isard source
COPY engine/engine /isard
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/src /opt/isardvdi/isardvdi_common

COPY engine/docker/genrsa.sh /
COPY engine/docker/run.sh /
COPY engine/docker/add-hypervisor.sh /
COPY engine/docker/add-hyper-rethink.py /

WORKDIR /isard

CMD ["/run.sh"]

FROM production as development
RUN apk add --no-cache --update bash vim openssh 
RUN apk add py3-yaml 

CMD ["sleep", "infinity"]
