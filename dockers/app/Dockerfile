FROM alpine:3.11.3 as test
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
	yarn \
        py3-libvirt==5.9.0-r0 \
	py3-paramiko==2.7.1-r0 \
	py3-lxml==4.4.2-r0 \
	py3-openssl==19.1.0-r0 \
	py3-bcrypt==3.1.7-r2 \
	py3-gevent==1.4.0-r2 \
	py3-flask==1.0.4-r0 \
	py3-netaddr==0.7.19-r4 \
	py3-requests==2.22.0-r0 \
        py3-pyldap==3.2.0-r1 \
        libvirt-client==5.9.0-r1 \
	curl==7.67.0-r0 \
	openssh-client==8.1_p1-r0 \
	sshpass==1.06-r0 \
	supervisor==4.1.0-r0

RUN apk add --no-cache --virtual .build_deps \
	build-base \
	python3-dev \
	libffi-dev \
	openssl-dev \
        libc-dev \
        libxml2-dev \
        libxslt-dev \
	gcc

RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir pandas
COPY dockers/app/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
#RUN pip3 list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip3 install -U && exit 0
#RUN pip3 install rethinkdb==2.3.0.post6  werkzeug==0.16.0 APScheduler==3.3.1 python-engineio==3.8.1
RUN apk del .build_deps

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
COPY dockers/app/add-hyper-rethink.py /
COPY dockers/app/supervisord.conf /etc/supervisord.conf

EXPOSE 5000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]


FROM test as development
RUN pip3 install --no-cache-dir ipython pytest
RUN apk add --no-cache --update bash vim openssh bash py3-pexpect

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
