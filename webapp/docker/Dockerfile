FROM alpine:3.22.0

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip yarn

COPY webapp/docker/requirements.txt .
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

# Copy the isard source
COPY webapp/webapp /isard

RUN cd /isard/webapp && yarn install
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
EXPOSE 5000
COPY webapp/docker/healthcheck.js /
HEALTHCHECK --interval=12s --timeout=12s --start-period=30s \
    CMD node /healthcheck.js
WORKDIR /isard
CMD [ "python3", "-u", "start.py" ]
STOPSIGNAL SIGINT
USER nobody