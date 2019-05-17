FROM alpine:3.8 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
	yarn \
	py3-libvirt \
	py3-paramiko \
	py3-lxml \
	py3-pexpect \
	py3-openssl \
	py3-bcrypt \
	py3-gevent \
	py3-flask \
	py3-netaddr \
	py3-requests \
	curl \
	openssh-client \
	supervisor

RUN apk add --no-cache --virtual .build_deps \
	build-base \
	python3-dev \
	libffi-dev \
	openssl-dev 
RUN pip3 install --no-cache-dir pandas
RUN apk del .build_deps

COPY dockers/app/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3

# Create the required directories
RUN mkdir -p /var/log/supervisor /isard /root/.ssh

# Configure SSH
RUN echo -e "Host isard-hypervisor\n \
	StrictHostKeyChecking no" >/root/.ssh/config
RUN chmod 600 /root/.ssh/config

# Copy the isard source
COPY ./src /isard
RUN mv /isard/isard.conf.docker /isard/isard.conf

COPY dockers/app/certs.sh /
COPY dockers/app/add-hypervisor.sh /
COPY dockers/app/supervisord.conf /etc/supervisord.conf

EXPOSE 5000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]

FROM production as development
RUN pip3 install --no-cache-dir ipython pytest
RUN apk add --no-cache --update bash vim openssh bash

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
