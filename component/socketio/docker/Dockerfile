FROM python:3.13-alpine3.22@sha256:e81548ac35b07a3bd4805f275107592ef458b1e893c0e04d45aedaa19416cca5 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

# Place the venv outside /app — devel mode bind-mounts
# ./component/socketio/src onto /app and would otherwise shadow
# /app/.venv (no uvicorn in the bind-mounted source). The
# UV_PROJECT_ENVIRONMENT path also pins the venv build location so
# the venv's hard-coded shebangs (#!/.venv/bin/python) keep
# resolving after the cross-stage COPY.
ENV UV_PROJECT_ENVIRONMENT=/.venv
WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-socketio --no-editable

FROM python:3.13-alpine3.22@sha256:e81548ac35b07a3bd4805f275107592ef458b1e893c0e04d45aedaa19416cca5 AS runtime
RUN apk add --no-cache libffi openssl

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/socketio/src /app
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "isardvdi_socketio:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*"]
