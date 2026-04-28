FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-scheduler --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi openssl tzdata

COPY --from=builder /workspace/.venv /.venv
COPY scheduler/src /src
ENV PATH="/.venv/bin:$PATH"
WORKDIR /src

CMD ["python3", "start.py"]
STOPSIGNAL SIGKILL
USER nobody
