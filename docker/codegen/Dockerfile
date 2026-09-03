# syntax=docker/dockerfile:1.7

FROM golang:1.25.12-alpine3.24@sha256:56961d79ea8129efddcc0b8643fd8a5416b4e6228cfd477e3fd61deb2672c587 AS go-build
ENV CGO_ENABLED=0
COPY docker/codegen/tools/go.mod docker/codegen/tools/go.sum /tools/
RUN --mount=type=cache,target=/root/.cache/go-build,sharing=locked \
    --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    cd /tools && go install tool

# NOTE: bun is pinned to 1.3.13-alpine (NOT :1.3-alpine, which currently
# resolves to 1.3.14). bun 1.3.14 has an intermittent tarball-extraction
# regression that fails on large packages as `error: Fail extracting tarball`
# — see bun#34821 (fixed by bun#34827, unreleased). Bump this pin once a
# fixed bun release ships.
FROM oven/bun:1.3.13-alpine@sha256:4de475389889577f346c636f956b42a5c31501b654664e9ae5726f94d7bb5349 AS node-build
WORKDIR /deps
COPY docker/codegen/tools/package.json docker/codegen/tools/bun.lock /deps/
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    bun install --frozen-lockfile

FROM ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine@sha256:43f1154bf7569ff82cab78d76ba6e6e553f99b6a2cc9c0b4c83615837f237650 AS py-build
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
COPY . .
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
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine@sha256:43f1154bf7569ff82cab78d76ba6e6e553f99b6a2cc9c0b4c83615837f237650 /usr/local/bin/python3.14 /usr/local/bin/python3.14
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine@sha256:43f1154bf7569ff82cab78d76ba6e6e553f99b6a2cc9c0b4c83615837f237650 /usr/local/lib/python3.14 /usr/local/lib/python3.14
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine@sha256:43f1154bf7569ff82cab78d76ba6e6e553f99b6a2cc9c0b4c83615837f237650 /usr/local/lib/libpython3.14.so.1.0 /usr/local/lib/libpython3.14.so.1.0
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine@sha256:43f1154bf7569ff82cab78d76ba6e6e553f99b6a2cc9c0b4c83615837f237650 /usr/local/bin/uv /usr/local/bin/uv
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
COPY docker/codegen/changefeed_utils.py /changefeed_utils.py
COPY docker/codegen/gen_changefeed_asyncapi.py /gen_changefeed_asyncapi.py
COPY docker/codegen/gen_changefeed_subscribers.py /gen_changefeed_subscribers.py
COPY docker/codegen/gen_changefeed_models.js /gen_changefeed_models.js

WORKDIR /build

CMD [ "/gen.sh" ]
