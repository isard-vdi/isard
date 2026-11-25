# syntax=docker/dockerfile:1.20

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
# Place the venv outside /app — devel mode bind-mounts
# ./component/openapi/src onto /app and would otherwise shadow
# /app/.venv (no uvicorn in the bind-mounted source). The
# UV_PROJECT_ENVIRONMENT path also pins the venv build location so
# the venv's hard-coded shebangs (#!/.venv/bin/python) keep
# resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-openapi --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-openapi --no-editable

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS runtime
RUN apk add --no-cache curl libffi openssl

ARG SWAGGER_UI_VERSION=5.32.14
ARG REDOC_VERSION=2.5.3

RUN mkdir -p /static \
 && curl -fsSL -o /static/swagger-ui-bundle.js https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui-bundle.js \
 && curl -fsSL -o /static/swagger-ui.css https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui.css \
 && curl -fsSL -o /static/redoc.standalone.js https://cdn.jsdelivr.net/npm/redoc@${REDOC_VERSION}/bundles/redoc.standalone.js

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/openapi/src /app
COPY pkg/oas /app/oas
COPY docker/swagger-ui/init.js /static/swagger-init.js
COPY component/frontend/src/assets/img/cover-img.svg /static/cover-img.svg
COPY component/frontend/public/favicon.ico /static/favicon.ico
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "isardvdi_openapi.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*"]
