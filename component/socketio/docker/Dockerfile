# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Copy the application code
ENV PYTHONPATH /opt/isardvdi
COPY component/socketio/src /opt/isardvdi/isardvdi_socketio
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common

# Install the dependencies. ``git`` is needed by pip to fetch the
# isard-vdi/rethinkdb-python fork from requirements.txt; dropped
# after install. ``RETHINKDB_FORK_SHA`` is resolved by CI per
# pipeline and busts the layer cache when the branch advances.
COPY component/socketio/docker/requirements.txt /tmp/
ARG RETHINKDB_FORK_SHA=unknown
RUN apk add --no-cache --virtual .build_deps git \
    && python3 -m venv venv \
    && echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build_deps

# Expose the port the app runs on
EXPOSE 5000

# uvicorn command
CMD ["venv/bin/uvicorn", "isardvdi_socketio:app", "--host", "0.0.0.0", "--port", "5000"]
