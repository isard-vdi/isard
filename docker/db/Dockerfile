# ---------- builder: build the isardvdi-db venv on the SAME base as runtime ----------
FROM rethinkdb:2.4.4-bookworm-slim@sha256:30e0235da35e645025ca755c50d9ba617765f7f186fd1b0879fe00177e14de6a AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=auto \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-db --no-editable

# ---------- runtime: rethinkdb + only the venv and its interpreter ----------
FROM rethinkdb:2.4.4-bookworm-slim@sha256:30e0235da35e645025ca755c50d9ba617765f7f186fd1b0879fe00177e14de6a

RUN apt-get update && \
    apt-get install -y \
        iproute2 \
        gawk \
        moreutils && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf \
        /var/lib/apt \
        /var/lib/dpkg \
        /var/lib/cache \
        /var/lib/log

# Bring only the built virtualenv and its uv-managed Python interpreter,
# NOT the whole build context. The previous single-stage `COPY . .` baked
# the entire monorepo into the db image (~5 GB); this drops it to ~350 MB.
COPY --from=builder /opt/uv/python /opt/uv/python
COPY --from=builder /workspace/.venv /workspace/.venv

ENV PATH="/workspace/.venv/bin:$PATH"
COPY docker/db/run.sh /run.sh

# Restore the base image's WORKDIR so rethinkdb's default data path
# (./rethinkdb_data) lands on the /data bind mount instead of the
# ephemeral container layer at /workspace.
WORKDIR /data

ENTRYPOINT [ "/bin/sh" ]
CMD [ "/run.sh" ]
