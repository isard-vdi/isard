# syntax=docker/dockerfile:1.7

FROM golang:1.25.8-alpine3.22@sha256:6b7607461f105ccaa0615b6f7932dfd5b36c5d827a0770b5578e565107cc3adb AS go-build
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

FROM ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine@sha256:4116326f5dc6815abc4d0a5a3846b735488ceb00cd3dc16da2a78577d30d6e0b AS py-build
ENV UV_COMPILE_BYTECODE=1 \
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

FROM alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce
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
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine@sha256:4116326f5dc6815abc4d0a5a3846b735488ceb00cd3dc16da2a78577d30d6e0b /usr/local/bin/python3.13 /usr/local/bin/python3.13
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine@sha256:4116326f5dc6815abc4d0a5a3846b735488ceb00cd3dc16da2a78577d30d6e0b /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine@sha256:4116326f5dc6815abc4d0a5a3846b735488ceb00cd3dc16da2a78577d30d6e0b /usr/local/lib/libpython3.13.so.1.0 /usr/local/lib/libpython3.13.so.1.0
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine@sha256:4116326f5dc6815abc4d0a5a3846b735488ceb00cd3dc16da2a78577d30d6e0b /usr/local/bin/uv /usr/local/bin/uv
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
