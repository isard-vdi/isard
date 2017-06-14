FROM fedora:latest
MAINTAINER isard <info@isard.com>

ENV INSTALL_PATH /isard
RUN mkdir -p $INSTALL_PATH
WORKDIR $INSTALL_PATH

COPY ./docker/engine/requirements.pip3 requirements.pip3
RUN dnf install wget gcc redhat-rpm-config python3-devel openssl-devel libvirt-devel -y
RUN pip3 install -r requirements.pip3

RUN dnf install openssh openssh-clients -y
COPY ./docker/engine/init.sh /
COPY ./docker/engine/config /root/.ssh/
COPY . .
COPY ./docker/isard.conf ./isard.conf

#CMD ./keys.sh;python3 /isard/run_engine.py
