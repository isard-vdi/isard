FROM alpine:3.12.0 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache \
    yarn \
    py3-openssl \
    py3-pyldap \
    py3-pip

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

# Create the required directories
RUN mkdir -p /var/log/supervisor /isard /root/.ssh

# Copy the isard source
COPY webapp/webapp /isard

RUN cd /isard/webapp && yarn install

EXPOSE 5000
WORKDIR /isard
CMD [ "python3", "start.py" ]

ARG SRC_VERSION_ID
ARG SRC_VERSION_LINK
RUN echo -n "$SRC_VERSION_ID" > /version
RUN echo -n "$SRC_VERSION_LINK" > /version_link
