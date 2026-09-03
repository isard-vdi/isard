FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-webapp --no-editable

FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssl yarn zlib

COPY --from=builder /.venv /.venv
COPY webapp/webapp /isard
COPY webapp/docker/healthcheck.js /
RUN cd /isard/webapp && yarn install --frozen-lockfile
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
HEALTHCHECK --interval=12s --timeout=12s --start-period=30s \
    CMD node /healthcheck.js
WORKDIR /isard
CMD ["python3", "-u", "start.py"]
STOPSIGNAL SIGINT
USER nobody
