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
rm -f ./*/**/testing_*_mock.go

mkdir -p /tmp/go
export HOME=/tmp
export GOPATH=/tmp/go

# Protobuf
source /venv/bin/activate
if [ -n "${BUF_TOKEN:+x}" ] && [ -n "$BUF_TOKEN" ]; then
  echo "Found buf token, authenticating with buf.build to avoid rate limits"
  export BUF_TOKEN
else
  echo "No buf token found, we may hit rate limits"
  unset BUF_TOKEN
fi
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
cd pkg/sdk && mockery && cd -
