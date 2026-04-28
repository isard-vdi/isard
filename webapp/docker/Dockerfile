FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-webapp --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache libffi libjpeg-turbo openssl yarn zlib

COPY --from=builder /workspace/.venv /.venv
COPY webapp/webapp /isard
COPY webapp/docker/healthcheck.js /
RUN cd /isard/webapp && yarn install
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
HEALTHCHECK --interval=12s --timeout=12s --start-period=30s \
    CMD node /healthcheck.js
WORKDIR /isard
CMD ["python3", "-u", "start.py"]
STOPSIGNAL SIGINT
USER nobody
