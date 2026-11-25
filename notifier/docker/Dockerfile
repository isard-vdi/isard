# syntax=docker/dockerfile:1.20

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

# UV_PROJECT_ENVIRONMENT points the venv at the runtime path so the
# venv's hard-coded shebangs (#!/.venv/bin/python) keep resolving
# after COPY --from=builder /.venv /.venv.
ENV UV_PROJECT_ENVIRONMENT=/.venv
WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev --package isardvdi-notifier --no-editable --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-notifier --no-editable

FROM python:3.14-alpine3.24@sha256:bc62fbcb684904b1bb81a6240041bb60e9c1ee19ddeaf17a6b4297e1cc9c95d2 AS runtime
RUN apk add --no-cache libffi openssl util-linux

COPY --from=builder /.venv /.venv
COPY notifier/src /isard

ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard

CMD ["/bin/sh", "-c", "rq worker --connection-class=isardvdi_common.connections.redis_retry.RedisRetry --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" notifier.default -n notifier:isard-notifier:$(uuidgen) -P /isard/notifier/lib & python3 -u /isard/start.py"]
USER nobody
