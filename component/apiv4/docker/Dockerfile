FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs (#!/app/.venv/bin/python) keep resolving
# after COPY --from=builder /app/.venv /app/.venv.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-apiv4 --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssh-client openssl ttf-liberation zlib

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY component/apiv4/src /app
COPY component/frontend/src/assets/logo.svg /usr/share/nginx/html/default_logo.svg
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
