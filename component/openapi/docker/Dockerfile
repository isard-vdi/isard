FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
# Place the venv outside /app — devel mode bind-mounts
# ./component/openapi/src onto /app and would otherwise shadow
# /app/.venv (no uvicorn in the bind-mounted source). The
# UV_PROJECT_ENVIRONMENT path also pins the venv build location so
# the venv's hard-coded shebangs (#!/.venv/bin/python) keep
# resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-openapi --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi openssl

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/openapi/src /app
COPY pkg/oas /app/oas
COPY component/frontend/src/assets/img/cover-img.svg /app/cover-img.svg
COPY component/frontend/public/favicon.ico /app/favicon.ico
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "isardvdi_openapi.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*"]
