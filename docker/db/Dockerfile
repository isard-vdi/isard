FROM rethinkdb:2.4.4-bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=auto \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

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

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-db --no-editable

ENV PATH="/workspace/.venv/bin:$PATH"
COPY docker/db/run.sh /run.sh

ENTRYPOINT [ "/bin/sh" ]
CMD [ "/run.sh" ]
