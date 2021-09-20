FROM alpine:latest as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    libc-dev \
    libxml2-dev \
    libxslt-dev \
    gcc \
    linux-headers

RUN apk add --no-cache python3 docker py3-libvirt
RUN apk add --no-cache py3-pip
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir setuptools_rust psutil requests docker xmltodict ipython flatten_dict redis rethinkdb==2.3.0.post6
RUN pip3 install --no-cache-dir influxdb-client
RUN pip3 install --no-cache-dir pyyaml

RUN apk add --no-cache py3-paramiko

RUN apk del .build_deps

RUN apk add util-linux \
    openssh-client \
    sshpass \
    socat

ADD docker/stats/src /src
WORKDIR /src
CMD ["/bin/sh", "run.sh"]
#CMD ["python3", "run.py"]

FROM production as development
CMD ["/sleep","10000"]
