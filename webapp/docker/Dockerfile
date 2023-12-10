FROM alpine:3.18 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    yarn \
    py3-openssl \
    py3-pip \
    py3-cachetools \
    curl

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
        libc-dev \
        libxml2-dev \
        libxslt-dev \
    gcc

# RUN apk upgrade openssh-client
RUN pip3 install --upgrade pip
COPY webapp/docker/requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt
RUN apk del .build_deps

# Copy the isard source
COPY webapp/webapp /isard

RUN cd /isard/webapp && yarn install
COPY component/_common/src /isard/webapp/_common
EXPOSE 5000
WORKDIR /isard
CMD [ "python3", "-u", "start.py" ]
STOPSIGNAL SIGINT
USER nobody