#!/bin/sh

# Protobuf
source /venv/bin/activate
export HOME=/tmp
buf generate

# Notifier OAS
mkdir -p pkg/gen/oas/notifier
oapi-codegen -generate types,client,spec -package notifier pkg/oas/notifier/notifier.json > pkg/gen/oas/notifier/notifier.gen.go
mockery --srcpkg ./pkg/gen/oas/notifier --name "Client.*Interface" --case underscore --inpackage --inpackage-suffix
