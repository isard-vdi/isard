FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-apiv4 --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssh-client openssl ttf-liberation zlib

WORKDIR /app
COPY --from=builder /workspace/.venv /app/.venv
COPY component/apiv4/src /app
COPY component/frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
