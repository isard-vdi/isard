# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Copy the application code
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/isardvdi_protobuf:/opt/isardvdi/asyncapi_changefeed
COPY component/change-handler/src /opt/isardvdi/isardvdi_change-handler
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf
COPY pkg/gen/asyncapi/changefeed /opt/isardvdi/asyncapi_changefeed

# Install the dependencies. ``git`` is needed by pip to fetch the
# isard-vdi/rethinkdb-python fork from requirements.txt
# (``git+https://...``); we drop it after the install. ``RETHINKDB_FORK_SHA``
# is resolved by CI per pipeline (see resolve-rethinkdb-fork-sha in
# .gitlab-ci.yml) and busts Docker's layer cache whenever the branch
# advances.
COPY component/change-handler/docker/requirements.txt /tmp/
ARG RETHINKDB_FORK_SHA=unknown
RUN apk add --no-cache --virtual .build_deps git \
    && python3 -m venv venv \
    && echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build_deps

# Start command
CMD ["venv/bin/python", "-m", "isardvdi_change-handler"]
STOPSIGNAL SIGTERM
