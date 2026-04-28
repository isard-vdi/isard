FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs (#!/app/.venv/bin/python) keep resolving
# after COPY --from=builder /app/.venv /app/.venv.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-core-worker --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi openssl

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY component/core_worker/src /app
COPY component/core_worker/docker/uuidgen.py /app/uuidgen.py
ENV PATH="/app/.venv/bin:$PATH"

CMD ["/bin/sh", "-c", "REDIS_WORKERS=${REDIS_WORKERS:-3}; for i in $(seq 1 $REDIS_WORKERS); do rq worker --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" --connection-class='isardvdi_common.connections.redis_retry.RedisRetry' core.feedback core -n core:isard-core_worker:$(python3 /app/uuidgen.py) -P /app/isardvdi_core_worker --with-scheduler & done; wait"]

USER nobody
