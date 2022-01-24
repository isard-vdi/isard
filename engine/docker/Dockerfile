FROM alpine:3.15.0 as production
MAINTAINER isard <info@isard.com>
WORKDIR /isard

RUN apk add --no-cache \
    yarn \
    py3-libvirt \
    py3-paramiko \
    py3-openssl \
    py3-bcrypt \
    py3-gevent \
    py3-flask \
    py3-netaddr \
    py3-numpy \
    py3-pyldap \
    py3-pip \
    libvirt-client \
    curl \
    openssh-client \
    sshpass \
    supervisor \
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
RUN pip3 install --upgrade pip
COPY engine/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r /requirements.pip3
RUN pip3 install tabulate pid
RUN apk del .build_deps

# Create the required directories
RUN mkdir -p /var/log/supervisor /isard /root/.ssh

# Configure SSH
RUN ssh-keygen -A
#RUN echo -e "Host isard-hypervisor\n \
#    StrictHostKeyChecking no" >/root/.ssh/config
#RUN chmod 600 /root/.ssh/config

RUN apk add --no-cache openssl shadow
RUN useradd -u 1000 -ms /bin/sh qemu
# Copy the isard source
COPY engine/engine /isard

COPY engine/docker/genrsa.sh /
COPY engine/docker/add-hypervisor.sh /
COPY engine/docker/add-hyper-rethink.py /
COPY engine/docker/supervisord.conf /etc/supervisord.conf


CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
HEALTHCHECK CMD curl -f http://localhost:5000/info

FROM production as development
RUN pip3 install --no-cache-dir ipython==7.26.0 ipython-genutils==0.2.0 pytest==6.2.4
RUN apk add --no-cache --update bash vim openssh 
RUN pip3 install python-telegram-bot
RUN apk add py3-yaml 

WORKDIR /isard
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
