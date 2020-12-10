FROM alpine:3.11.3 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
    yarn \
    py3-paramiko==2.7.1-r0 \
    py3-lxml==4.4.2-r0 \
    py3-openssl==19.1.0-r0 \
    py3-bcrypt==3.1.7-r2 \
    py3-gevent==1.4.0-r2 \
    py3-flask==1.0.4-r0 \
    py3-netaddr==0.7.19-r4 \
    py3-requests==2.22.0-r0 \
        py3-pyldap==3.2.0-r1 \
    curl~=7.67.0 \
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

RUN apk upgrade openssh-client
RUN pip3 install --upgrade pip
COPY webapp/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

# Create the required directories
RUN mkdir -p /var/log/supervisor /isard /root/.ssh

# Copy the isard source
COPY webapp/webapp /isard

COPY webapp/docker/supervisord.conf /etc/supervisord.conf

EXPOSE 5000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]

FROM production as development
RUN pip3 install --no-cache-dir ipython pytest
RUN apk add --no-cache --update bash vim openssh 
RUN pip3 install python-telegram-bot
RUN apk add py3-yaml 

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
