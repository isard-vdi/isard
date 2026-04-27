FROM alpine:3.22.0 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip curl py3-gevent py3-greenlet tzdata

RUN pip3 install --break-system-package --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    git
COPY scheduler/docker/requirements.txt /requirements.txt
# ``RETHINKDB_FORK_SHA`` is resolved by CI per pipeline (see
# resolve-rethinkdb-fork-sha in .gitlab-ci.yml) and busts Docker's
# layer cache when the modernize-python-client branch tip advances.
ARG RETHINKDB_FORK_SHA=unknown
RUN echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && pip3 install --break-system-package --no-cache-dir -r requirements.txt
RUN apk del .build_deps

COPY scheduler/src /src
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
WORKDIR /src

CMD ["python3", "start.py"]
STOPSIGNAL SIGKILL
USER nobody
