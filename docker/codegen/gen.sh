#!/bin/sh

set -e

rm -rf pkg/gen
rm -rf frontend/src/gen

# Protobuf
source /venv/bin/activate
export HOME=/tmp
buf generate

# Notifier OAS
mkdir -p pkg/gen/oas/notifier
ogen --target ./pkg/gen/oas/notifier -package notifier --clean pkg/oas/notifier/notifier.json

# Authentication OAS
mkdir -p pkg/gen/oas/authentication
ogen --target ./pkg/gen/oas/authentication -package authentication --clean pkg/oas/authentication/authentication.json
cd frontend
CODEGEN=authentication openapi-ts
cd -

# Go mocks
mockery
