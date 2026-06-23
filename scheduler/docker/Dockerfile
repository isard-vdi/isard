FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/
# UV_PROJECT_ENVIRONMENT pins the venv at the runtime path so the
# venv's hard-coded shebangs keep resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-scheduler --no-editable

FROM python:3.13-alpine AS runtime
RUN apk add --no-cache curl libffi openssl tzdata

COPY --from=builder /.venv /.venv
COPY scheduler/src /src
ENV PATH="/.venv/bin:$PATH"
WORKDIR /src

CMD ["python3", "start.py"]
STOPSIGNAL SIGKILL
USER nobody
