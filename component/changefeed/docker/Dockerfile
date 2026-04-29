FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
# Place the venv outside /app — devel mode bind-mounts
# ./component/changefeed/src onto /app and would otherwise shadow
# /app/.venv. UV_PROJECT_ENVIRONMENT also pins the venv build
# location so the venv's hard-coded shebangs (#!/.venv/bin/python)
# keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-changefeed --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi openssl

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/changefeed/src /app
ENV PATH="/.venv/bin:$PATH"
CMD ["python", "-m", "isardvdi_changefeed"]
STOPSIGNAL SIGTERM
