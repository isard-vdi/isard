# syntax=docker/dockerfile:1.20

FROM golang:1.26.10-alpine3.24@sha256:9ce231b28998b32e116927c61aa5c406183061d4f3f2d61b292c88e7f6bdf7ca AS go-build
ENV CGO_ENABLED=0
COPY docker/codegen/tools/go.mod docker/codegen/tools/go.sum /tools/
RUN --mount=type=cache,target=/root/.cache/go-build,sharing=locked \
    --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    cd /tools && go install tool

FROM oven/bun:1.4.4-alpine@sha256:4cf82f5686b196504fe119db3fcd9185b191f82ece82c40680e597228ec6070a AS node-build
WORKDIR /deps
COPY docker/codegen/tools/package.json docker/codegen/tools/bun.lock /deps/
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    bun install --frozen-lockfile

FROM ghcr.io/astral-sh/uv:0.13.6-python3.14-alpine@sha256:a069b57ec30ef94da43700a7332b162a13adb0b8a1cfba4e0b62c1a9727153c4 AS py-build
# UV_COMPILE_BYTECODE=0: uv fans its bytecode compiler out over every core, and
# on a 192-core host that exhausts file descriptors mid-walk —
#   error: Failed to bytecode-compile Python file in /venv/.../site-packages
#     Caused by: No file descriptors available (os error 24)
# which aborts build.sh (set -e) before a single service image is built.
# Reproduced on a 192-core host: =1 fails at 2.0s, =0 completes in 1.5s.
# This is a build-time generator image; precompiled bytecode only saves a few
# ms of interpreter startup, so dropping it costs nothing measurable.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_PROGRESS=1 \
    UV_PROJECT_ENVIRONMENT=/venv
RUN apk add --no-cache \
        build-base \
        libffi-dev \
        libjpeg-turbo-dev \
        musl-dev \
        openssl-dev \
        zlib-dev
WORKDIR /workspace
COPY --parents ./**/pyproject.toml ./uv.lock ./.python-version ./
RUN uv sync --frozen --no-dev \
        --package isardvdi-codegen \
        --no-editable \
        --no-install-workspace
COPY docker/codegen/src ./docker/codegen/src
RUN uv sync --frozen --no-dev \
        --package isardvdi-codegen \
        --no-editable && \
    chmod -R a+w /venv

FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b
RUN apk -U upgrade --no-cache && \
    apk add --no-cache \
        protoc \
        grpc-plugins \
        libffi \
        libjpeg-turbo \
        libstdc++ \
        openssl \
        zlib

COPY --from=go-build /usr/local/go /usr/local/go
COPY --from=go-build /go/bin/ /usr/local/bin/
COPY --from=node-build /usr/local/bin/bun /usr/local/bin/bun
COPY --from=node-build /deps/ /deps/
COPY --from=ghcr.io/astral-sh/uv:0.13.6-python3.14-alpine@sha256:a069b57ec30ef94da43700a7332b162a13adb0b8a1cfba4e0b62c1a9727153c4 /usr/local/bin/python3.14 /usr/local/bin/python3.14
COPY --from=ghcr.io/astral-sh/uv:0.13.6-python3.14-alpine@sha256:a069b57ec30ef94da43700a7332b162a13adb0b8a1cfba4e0b62c1a9727153c4 /usr/local/lib/python3.14 /usr/local/lib/python3.14
COPY --from=ghcr.io/astral-sh/uv:0.13.6-python3.14-alpine@sha256:a069b57ec30ef94da43700a7332b162a13adb0b8a1cfba4e0b62c1a9727153c4 /usr/local/lib/libpython3.14.so.1.0 /usr/local/lib/libpython3.14.so.1.0
COPY --from=ghcr.io/astral-sh/uv:0.13.6-python3.14-alpine@sha256:a069b57ec30ef94da43700a7332b162a13adb0b8a1cfba4e0b62c1a9727153c4 /usr/local/bin/uv /usr/local/bin/uv
COPY --from=py-build /venv /venv

RUN ln -s bun /usr/local/bin/node && \
    chmod 777 /venv

ENV GOTOOLCHAIN=local \
    GOPATH=/cache/go \
    GOCACHE=/cache/go-build \
    UV_CACHE_DIR=/cache/uv \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:/deps/node_modules/.bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/sbin:/bin

COPY docker/codegen/gen.sh /gen.sh
COPY docker/codegen/gen_changefeed_models.js /gen_changefeed_models.js

WORKDIR /build

CMD [ "/gen.sh" ]
