FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-changefeed --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi openssl

WORKDIR /app
COPY --from=builder /workspace/.venv /app/.venv
COPY component/changefeed/src /app
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "isardvdi_changefeed"]
STOPSIGNAL SIGTERM
