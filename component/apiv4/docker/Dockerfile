# syntax=docker/dockerfile:1.20

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

# Place the venv outside /app — devel mode bind-mounts
# ./component/apiv4/src onto /app and would otherwise shadow
# /app/.venv (no uvicorn/pip in the bind-mounted source). The
# UV_PROJECT_ENVIRONMENT path also pins the venv build location so
# the venv's hard-coded shebangs (#!/.venv/bin/python) keep
# resolving after the cross-stage COPY.
ENV UV_PROJECT_ENVIRONMENT=/.venv
WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-apiv4 --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-apiv4 --no-editable

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssh-client openssl ttf-liberation zlib

ARG SRC_VERSION_ID
RUN echo -n "$SRC_VERSION_ID" > /version
ARG SRC_COMMIT_SHA
RUN echo -n "$SRC_COMMIT_SHA" > /commit

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/apiv4/src /app
COPY component/frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg
COPY component/frontend/src/assets/logo-collapsed.svg /usr/share/nginx/html/default_logo_collapsed.svg
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*", "--timeout-keep-alive", "120"]
