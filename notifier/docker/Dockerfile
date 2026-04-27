FROM alpine:3.22.0

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip uuidgen

COPY notifier/docker/requirements.txt .
# ``RETHINKDB_FORK_SHA`` is resolved by CI per pipeline (see
# resolve-rethinkdb-fork-sha in .gitlab-ci.yml) and busts Docker's
# layer cache when the modernize-python-client branch tip advances.
# git is needed only at install time for pip's git+https fetch.
ARG RETHINKDB_FORK_SHA=unknown
RUN apk add --no-cache --virtual .build_deps git \
    && echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && pip install -r requirements.txt --break-system-package \
    && rm requirements.txt \
    && apk del .build_deps
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY notifier/src /opt/isardvdi/src
WORKDIR /opt/isardvdi/src

CMD ["/bin/sh", "-c", "rq worker --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" notifier.default -n notifier:isard-notifier:$(uuidgen) -P /opt/isardvdi/src/notifier/lib & python3 -u /opt/isardvdi/src/start.py"]
USER nobody