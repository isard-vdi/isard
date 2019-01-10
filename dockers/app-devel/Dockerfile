FROM isard/alpine-pandas:latest
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache git bash yarn py3-libvirt py3-paramiko py3-lxml py3-pexpect py3-openssl py3-bcrypt py3-gevent py3-flask py3-netaddr py3-requests curl openssh-client
RUN apk add --no-cache git

######## only devel ########
#RUN mkdir /isard
#ADD ./src /isard
############################

######## only devel ########
COPY dockers/app-devel/requirements.pip3 /requirements.pip3
############################

RUN pip3 install --no-cache-dir -r requirements.pip3

######## only devel ########
RUN pip3 install ipython pytest
#not run in devel
#RUN mv /isard/isard.conf.docker /isard/isard.conf
############################

RUN mkdir -p /root/.ssh
RUN echo "Host isard-hypervisor \
	StrictHostKeyChecking no" >/root/.ssh/config
RUN chmod 600 /root/.ssh/config

RUN apk add --update bash
RUN apk add yarn
RUN apk add openssh-client

######## only devel ########
RUN apk add vim openssh
############################

RUN apk add supervisor
RUN mkdir -p /var/log/supervisor

######## only devel ########
COPY dockers/app-devel/supervisord.conf /etc/supervisord.conf
############################

COPY dockers/app/certs.sh /
CMD /usr/bin/supervisord -c /etc/supervisord.conf
#CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
#CMD ["sh", "/init.sh"]
