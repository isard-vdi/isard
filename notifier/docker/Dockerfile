FROM python:3.13-alpine3.22@sha256:e81548ac35b07a3bd4805f275107592ef458b1e893c0e04d45aedaa19416cca5 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

# UV_PROJECT_ENVIRONMENT points the venv at the runtime path so the
# venv's hard-coded shebangs (#!/.venv/bin/python) keep resolving
# after COPY --from=builder /.venv /.venv.
ENV UV_PROJECT_ENVIRONMENT=/.venv
WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-notifier --no-editable

FROM python:3.13-alpine3.22@sha256:e81548ac35b07a3bd4805f275107592ef458b1e893c0e04d45aedaa19416cca5 AS runtime
RUN apk add --no-cache libffi openssl util-linux

COPY --from=builder /.venv /.venv
COPY notifier/src /isard

ENV PATH="/.venv/bin:$PATH"
WORKDIR /isard

CMD ["/bin/sh", "-c", "rq worker --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" notifier.default -n notifier:isard-notifier:$(uuidgen) -P /isard/notifier/lib & python3 -u /isard/start.py"]
USER nobody
