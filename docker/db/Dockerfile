# syntax=docker/dockerfile:1.20

# ---------- builder: build the isardvdi-db venv on the SAME base as runtime ----------
FROM rethinkdb:2.4.4-bookworm-slim@sha256:2a19a4d4a7351fba859bdd02fb3d8e0ec942104c618fe4585707ddaf4470e6a7 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=auto \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-db --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-db --no-editable

# ---------- runtime: rethinkdb + only the venv and its interpreter ----------
FROM rethinkdb:2.4.4-bookworm-slim@sha256:2a19a4d4a7351fba859bdd02fb3d8e0ec942104c618fe4585707ddaf4470e6a7

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
