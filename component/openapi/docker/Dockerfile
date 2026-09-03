FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /usr/local/bin/
# Place the venv outside /app — devel mode bind-mounts
# ./component/openapi/src onto /app and would otherwise shadow
# /app/.venv (no uvicorn in the bind-mounted source). The
# UV_PROJECT_ENVIRONMENT path also pins the venv build location so
# the venv's hard-coded shebangs (#!/.venv/bin/python) keep
# resolving after the cross-stage COPY.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/.venv

RUN apk add --no-cache build-base libffi-dev musl-dev openssl-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-openapi --no-editable

FROM python:3.14-alpine3.24@sha256:a1321512d6a287428c50dcdf2ab3857761127e03a23b1f648e9c1c0de59288f8 AS runtime
RUN apk add --no-cache curl libffi openssl

ARG SWAGGER_UI_VERSION=5.32.14
ARG REDOC_VERSION=2.5.3

RUN mkdir -p /static \
 && curl -fsSL -o /static/swagger-ui-bundle.js https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui-bundle.js \
 && curl -fsSL -o /static/swagger-ui.css https://cdn.jsdelivr.net/npm/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui.css \
 && curl -fsSL -o /static/redoc.standalone.js https://cdn.jsdelivr.net/npm/redoc@${REDOC_VERSION}/bundles/redoc.standalone.js

WORKDIR /app
COPY --from=builder /.venv /.venv
COPY component/openapi/src /app
COPY pkg/oas /app/oas
COPY docker/swagger-ui/init.js /static/swagger-init.js
COPY component/frontend/src/assets/img/cover-img.svg /static/cover-img.svg
COPY component/frontend/public/favicon.ico /static/favicon.ico
ENV PATH="/.venv/bin:$PATH"
EXPOSE 5000
CMD ["uvicorn", "isardvdi_openapi.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--forwarded-allow-ips=*"]
