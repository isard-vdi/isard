#!/bin/sh

set -e

openapi_ts() {
	ln -s /deps/package.json .
	ln -s /deps/node_modules .

	CODEGEN="$1" npx --no @hey-api/openapi-ts

	rm package.json
	rm node_modules
}

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
openapi_ts authentication

# API OAS
mkdir -p pkg/gen/oas/api
ogen --target ./pkg/gen/oas/api -package api --clean pkg/oas/api/api.json
openapi_ts api

# Go mocks
mockery
