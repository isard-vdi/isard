FROM isard/alpine-pandas:latest
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache bash yarn py3-libvirt py3-paramiko py3-lxml py3-pexpect py3-openssl py3-bcrypt py3-gevent py3-flask py3-netaddr py3-requests curl openssh-client

COPY dockers/app/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3

RUN mkdir -p /root/.ssh
RUN echo "Host isard-hypervisor \
	StrictHostKeyChecking no" >/root/.ssh/config
RUN chmod 600 /root/.ssh/config

RUN apk add --no-cache supervisor
RUN mkdir -p /var/log/supervisor
COPY dockers/app/supervisord.conf /etc/supervisord.conf

EXPOSE 5000

COPY dockers/app/certs.sh /
COPY dockers/app/add-hypervisor.sh /

RUN mkdir /isard
ADD ./src /isard
RUN mv /isard/isard.conf.docker /isard/isard.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
