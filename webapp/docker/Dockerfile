# syntax=docker/dockerfile:1.20

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-webapp --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-webapp --no-editable

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssl yarn zlib

COPY --from=builder /.venv /.venv
COPY webapp/src /isard
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
