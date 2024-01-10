#!/bin/sh

rm -rf pkg/gen

# Protobuf
source /venv/bin/activate
export HOME=/tmp
buf generate

# Notifier OAS
mkdir -p pkg/gen/oas/notifier
ogen --target ./pkg/gen/oas/notifier -package notifier --clean pkg/oas/notifier/notifier.json
mockery --srcpkg ./pkg/gen/oas/notifier --name "Invoker" --case underscore --inpackage --inpackage-suffix

# Authentication OAS
mkdir -p pkg/gen/oas/authentication
ogen --target ./pkg/gen/oas/authentication -package authentication --clean pkg/oas/authentication/authentication.json
mockery --srcpkg ./pkg/gen/oas/authentication --name "Invoker" --case underscore --inpackage --inpackage-suffix
mockery --srcpkg ./pkg/gen/oas/authentication --name "Handler" --case underscore --inpackage --inpackage-suffix
