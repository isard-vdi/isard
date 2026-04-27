# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Copy the application code
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/asyncapi_changefeed
COPY component/changefeed/src /opt/isardvdi/isardvdi_changefeed
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/asyncapi/changefeed /opt/isardvdi/asyncapi_changefeed

# Install the dependencies. ``git`` is needed by pip to fetch the
# isard-vdi/rethinkdb-python fork from requirements.txt; dropped
# after the install. ``RETHINKDB_FORK_SHA`` is set by CI and busts
# the layer cache when the branch advances.
COPY component/changefeed/docker/requirements.txt /tmp/
ARG RETHINKDB_FORK_SHA=unknown
RUN apk add --no-cache --virtual .build_deps git \
    && python3 -m venv venv \
    && echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build_deps

# Start command
CMD ["venv/bin/python", "-m", "isardvdi_changefeed"]
STOPSIGNAL SIGTERM
