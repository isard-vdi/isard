FROM alpine:3.22.0 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    py3-libvirt \
    py3-paramiko \
    py3-openssl \
    py3-bcrypt \
    py3-flask \
    py3-pip \
    openssh-client \
    libvirt-client \
    curl \
    sshpass \
    pciutils-libs \
    hwids-pci

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \
    libc-dev \
    libxml2-dev \
    libxslt-dev \
    gcc \
    git

RUN apk upgrade openssh-client
RUN pip3 install --upgrade pip --break-system-package
COPY engine/docker/requirements.txt /requirements.txt
# ``RETHINKDB_FORK_SHA`` is resolved by CI per pipeline (see
# resolve-rethinkdb-fork-sha in .gitlab-ci.yml) and busts Docker's
# layer cache when the modernize-python-client branch tip advances.
ARG RETHINKDB_FORK_SHA=unknown
RUN echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && pip3 install --no-cache-dir -r /requirements.txt --break-system-package
RUN apk del .build_deps

RUN apk add --no-cache openssl shadow
RUN useradd -u 1000 -ms /bin/sh qemu
# Copy the isard source
COPY engine/engine /isard
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/asyncapi_changefeed
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/asyncapi/changefeed /opt/isardvdi/asyncapi_changefeed

COPY engine/docker/genrsa.sh /
COPY engine/docker/run.sh /
COPY engine/docker/add-hypervisor.sh /

WORKDIR /isard

CMD ["/run.sh"]

FROM production as development
RUN apk add --no-cache --update bash vim openssh 
RUN apk add py3-yaml 

CMD ["sleep", "infinity"]
