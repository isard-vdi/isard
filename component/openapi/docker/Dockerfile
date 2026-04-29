FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-openapi --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi openssl

WORKDIR /app
COPY --from=builder /workspace/.venv /app/.venv
COPY component/openapi/src /app
COPY pkg/oas /app/oas
COPY component/frontend/src/assets/img/cover-img.svg /app/cover-img.svg
COPY component/frontend/public/favicon.ico /app/favicon.ico
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "isardvdi_openapi.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*"]
