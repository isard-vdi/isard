FROM alpine:3.12.0 as production
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache --update wireguard-tools openssh python3
RUN rm -rf /etc/ssh/ssh_host_rsa_key /etc/ssh/ssh_host_dsa_key
COPY docker/vpn/src /src
COPY docker/vpn/run.sh /

## From isard-api
RUN apk add python3 py3-pip
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev 
COPY docker/vpn/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

## End

CMD [ "sh", "run.sh"]

