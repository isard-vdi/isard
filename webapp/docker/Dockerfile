FROM alpine:3.15.0 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
    yarn \
    py3-openssl \
    py3-pip \
    py3-cachetools

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
COPY webapp/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

# Copy the isard source
COPY webapp/webapp /isard

RUN cd /isard/webapp && yarn install

EXPOSE 5000
WORKDIR /isard
CMD [ "python3", "-u", "start.py" ]
HEALTHCHECK --interval=10s CMD wget -qO /dev/null http://localhost:5000/isard-admin/healthcheck
STOPSIGNAL SIGINT
