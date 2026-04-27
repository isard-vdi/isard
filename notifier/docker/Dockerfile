FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-notifier --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi openssl util-linux

COPY --from=builder /workspace/.venv /.venv
COPY notifier/src /isard

ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard

CMD ["/bin/sh", "-c", "rq worker --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" notifier.default -n notifier:isard-notifier:$(uuidgen) -P /isard/notifier/lib & python3 -u /isard/start.py"]
USER nobody
