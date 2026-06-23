# syntax=docker/dockerfile:1.7

FROM golang:1.25.8-alpine3.22 AS go-build
ENV CGO_ENABLED=0
RUN --mount=type=cache,target=/root/.cache/go-build,sharing=locked \
    --mount=type=cache,target=/go/pkg/mod,sharing=locked \
    go install github.com/bufbuild/buf/cmd/buf@v1.50.0 && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1 && \
    go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@v1.5.1 && \
    go install github.com/ogen-go/ogen/cmd/ogen@v1.4.1 && \
    go install github.com/vektra/mockery/v2@v2.53.6

FROM oven/bun:1.3-alpine AS node-build
WORKDIR /deps
RUN --mount=type=cache,target=/root/.bun/install/cache,sharing=locked \
    bun add \
        @bufbuild/protoc-gen-es@2.6.0 \
        @bufbuild/protobuf@2.6.0 \
        @bufbuild/protoplugin@2.6.0 \
        @hey-api/openapi-ts@0.92.4 \
        @asyncapi/parser@3.6.0 \
        @asyncapi/modelina@5.10.1

FROM ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine AS py-build
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

FROM alpine:3.22
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
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine /usr/local/bin/python3.13 /usr/local/bin/python3.13
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine /usr/local/lib/libpython3.13.so.1.0 /usr/local/lib/libpython3.13.so.1.0
COPY --from=ghcr.io/astral-sh/uv:0.11.23-python3.13-alpine /usr/local/bin/uv /usr/local/bin/uv
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
