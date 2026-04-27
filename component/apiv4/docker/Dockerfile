# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# System packages: fonts-liberation is needed by gen_image.py to generate
# placeholder desktop card images via PIL.ImageFont.truetype(). git is
# needed by pip to fetch the isard-vdi/rethinkdb-python fork from
# requirements.txt (``git+https://...``); we drop it after install to
# keep the runtime image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation openssh-client git \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY component/apiv4/docker/requirements.txt .

# Install the dependencies. ``RETHINKDB_FORK_SHA`` is the current
# branch HEAD of isard-vdi/rethinkdb-python @ modernize-python-client.
# CI resolves it once per pipeline (see ``resolve-rethinkdb-fork-sha``
# in .gitlab-ci.yml) and passes it via ``--build-arg``. The ``echo``
# embeds the SHA in the layer command so Docker's layer cache
# invalidates whenever the branch advances — without it, the layer
# would stay cached on the first SHA seen and pip would never
# refetch.
ARG RETHINKDB_FORK_SHA=unknown
RUN echo "rethinkdb fork SHA at build: ${RETHINKDB_FORK_SHA}" \
    && pip install --no-cache-dir -r requirements.txt --break-system-package \
    && apt-get purge -y git \
    && apt-get autoremove -y

# Copy the rest of the application code
COPY component/apiv4/src .

# Import isardvdi_common package
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/isardvdi_protobuf
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf

# Default logo fallback (same asset used by isard-static)
COPY component/frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]