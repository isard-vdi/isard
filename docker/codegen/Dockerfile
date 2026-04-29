FROM golang:1.25.8-alpine3.22

ENV GODEBUG=netdns=go+4

# Stable apk layers — collapsed into one RUN so we don't carry a
# second apt metadata layer.
RUN apk -U upgrade --no-cache && \
    apk add --no-cache \
        python3 \
        npm \
        protoc \
        grpc-plugins \
        build-base \
        libffi-dev \
        libjpeg-turbo-dev \
        musl-dev \
        openssl-dev \
        zlib-dev

# Go codegen tools (~1.71 GB). Pinned versions; only invalidates on
# explicit bump.
RUN go install github.com/bufbuild/buf/cmd/buf@v1.50.0 && \
  go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
  go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1 && \
  go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@v1.5.1 && \
  go install github.com/ogen-go/ogen/cmd/ogen@v1.4.1 && \
  go install github.com/vektra/mockery/v2@v2.53.6

# uv binary (~58 MB) — pinned.
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=auto UV_PYTHON_INSTALL_DIR=/opt/uv/python

# Global npm codegen plugins (~58 MB) — pinned.
RUN npm install -g \
    @bufbuild/protoc-gen-es@2.6.0 \
    @bufbuild/protobuf@2.6.0 \
    @bufbuild/protoplugin@2.6.0 \
    @bufbuild/protoc-gen-es@2.6.0

# Project-local npm codegen tools (~2 GB total). Kept above the
# repo COPY so any commit that touches /workspace doesn't blow
# this layer away — the previous order rebuilt 2 GB on every
# codegen run.
WORKDIR /deps
RUN npm install \
    @hey-api/openapi-ts@0.92.4 \
    @asyncapi/cli@6.0.0 && \
    mkdir -p /deps/node_modules/@asyncapi/cli/lib/utils/logs

# === stable toolchain ends here =================================
# Everything below this line invalidates per-repo-change.

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-codegen --package isardvdi-apiv4 --no-editable

RUN ln -s /workspace/.venv /apiv4-venv && \
    ln -s /workspace/.venv /venv

COPY docker/codegen/gen.sh /gen.sh
COPY docker/codegen/changefeed_utils.py /changefeed_utils.py
COPY docker/codegen/gen_changefeed_asyncapi.py /gen_changefeed_asyncapi.py
COPY docker/codegen/gen_changefeed_subscribers.py /gen_changefeed_subscribers.py

WORKDIR /build

CMD [ "/gen.sh" ]
