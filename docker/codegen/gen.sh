#!/bin/sh

set -e

openapi_go() {
	mkdir -p "pkg/gen/oas/$1"
	if [ -n "$3" ]; then
		run_quietly ogen --target "./pkg/gen/oas/$1" -package "$1" --clean --config "$3" "$2"
	else
		run_quietly ogen --target "./pkg/gen/oas/$1" -package "$1" --clean "$2"
	fi && echo "  generated Go client: $1"
}

openapi_ts() {
	CODEGEN="$1" run_quietly openapi-ts \
		&& echo "  generated TypeScript client: $1"
}

openapi_ts_e2e() {
	CODEGEN="$1" CODEGEN_TARGET=e2e run_quietly openapi-ts \
		&& echo "  generated TypeScript client (e2e): $1"
}

openapi_python() {
	run_quietly openapi-python-client generate \
		--path "$2" \
		--output-path "component/_common/$1/src/$1" \
		--overwrite \
		--config "component/_common/$1/openapi-python-client.yml" \
		--meta=none \
		&& echo "  generated Python client: $1"
}

run_quietly() {
	log=$(mktemp)
	if "$@" >"$log" 2>&1; then
		rm -f "$log"
	else
		rc=$?
		cat "$log" >&2
		rm -f "$log"
		return "$rc"
	fi
}

rm -rf pkg/gen/proto/go
rm -rf pkg/gen/proto/docs
rm -rf pkg/gen/proto/js
rm -rf pkg/gen/proto/python/src
rm -rf pkg/gen/oas
rm -rf pkg/gen/asyncapi/changefeed/changefeed_models
rm -rf pkg/gen/asyncapi/changefeed/changefeed_subscribers
rm -f pkg/gen/asyncapi/changefeed/changefeed.yaml
rm -rf component/frontend/src/gen
rm -rf testing/e2e/src/gen
rm -rf component/_common/isardvdi_apiv4_client/src/isardvdi_apiv4_client
rm -rf component/_common/isardvdi_authentication_client/src/isardvdi_authentication_client
rm -rf component/_common/isardvdi_notifier_client/src/isardvdi_notifier_client
rm -rf component/_common/isardvdi_scheduler_client/src/isardvdi_scheduler_client
rm -f ./*/**/testing_*_mock.go

mkdir -p "$GOPATH" "$GOCACHE"
export HOME=/tmp

# Symlinks needed by openapi-ts; created once at the top so they don't race
# when multiple jobs run in parallel.
ln -sf /deps/package.json .
ln -sf /deps/node_modules .

# Resolve modelina + parser for the changefeed-models script.
export NODE_PATH=/deps/node_modules

. /venv/bin/activate

# POSIX-sh helper to track parallel jobs (no arrays in busybox sh).
JOB_PIDS=""
wait_jobs() {
	rc=0
	for pid in $JOB_PIDS; do
		wait "$pid" || rc=$?
	done
	JOB_PIDS=""
	if [ "$rc" -ne 0 ]; then
		exit "$rc"
	fi
}

echo "==> Phase 1: protobuf + service clients (notifier, scheduler, authentication) (parallel)"

(
	set -e
	run_quietly buf generate
	# Mark isardvdi_protobuf as a package so the src-layout wheel can import it.
	touch pkg/gen/proto/python/src/isardvdi_protobuf/__init__.py
	# Rewrite bare sibling imports in generated grpcio *_pb2_grpc.py files to
	# use the isardvdi_protobuf. package prefix.
	python3 -c "
import re, pathlib
grpc_dir = pathlib.Path('pkg/gen/proto/python/src/isardvdi_protobuf')
for f in grpc_dir.rglob('*_pb2_grpc.py'):
    text = f.read_text()
    new_text = re.sub(r'^(from )([a-z_]+)(\.v\d+ import \S+)', r'\1isardvdi_protobuf.\2\3', text, flags=re.MULTILINE)
    if new_text != text:
        f.write_text(new_text)
"
	echo "  generated protobuf bindings (Go + Python + docs + JS)"
) &
JOB_PIDS="$JOB_PIDS $!"

(
	set -e
	openapi_go notifier pkg/oas/notifier/notifier.json pkg/oas/ogen-client.yml
	openapi_python isardvdi_notifier_client pkg/oas/notifier/notifier.json
) &
JOB_PIDS="$JOB_PIDS $!"

(
	set -e
	openapi_go scheduler pkg/oas/scheduler/scheduler.json pkg/oas/ogen-client.yml
	openapi_python isardvdi_scheduler_client pkg/oas/scheduler/scheduler.json
) &
JOB_PIDS="$JOB_PIDS $!"

# Authentication: Python client must exist before gen_openapi.py runs in
# Phase 2 (apiv4's services/migrations.py imports isardvdi_authentication_client
# at module level).
(
	set -e
	openapi_go authentication pkg/oas/authentication/authentication.json pkg/oas/ogen-server.yml
	openapi_ts authentication || echo "WARNING: openapi_ts authentication failed"
	openapi_python isardvdi_authentication_client pkg/oas/authentication/authentication.json
) &
JOB_PIDS="$JOB_PIDS $!"

wait_jobs

# The image only ships codegen tools in the venv; apiv4 + its workspace
# deps (now with real Phase-1 source) install here against the offline uv
# cache shipped in the image.
run_quietly uv sync --frozen --no-dev \
	--package isardvdi-codegen \
	--package isardvdi-apiv4 \
	--no-editable \
	&& echo "  installed apiv4 + workspace packages"

echo "==> Phase 2: APIv4 OpenAPI spec + changefeed (parallel)"

# Changefeed AsyncAPI: input is tables.json, independent of APIv4 OAS.
# Runs in parallel with gen_openapi.py.
(
	set -e
	mkdir -p pkg/gen/asyncapi/changefeed
	run_quietly python /gen_changefeed_asyncapi.py \
		--tables component/changefeed/src/isardvdi_changefeed/tables.json \
		--output pkg/gen/asyncapi/changefeed/changefeed.yaml \
		&& echo "  generated changefeed AsyncAPI spec"
	# Generate into a directory matching --packageName so that
	# ``from changefeed_models.domains_change import DomainsChange`` works
	# once ``pkg/gen/asyncapi/changefeed`` is on PYTHONPATH.
	run_quietly bun run /gen_changefeed_models.js \
		pkg/gen/asyncapi/changefeed/changefeed.yaml \
		pkg/gen/asyncapi/changefeed/changefeed_models \
		changefeed_models \
		&& echo "  generated changefeed Python models"
	touch pkg/gen/asyncapi/changefeed/changefeed_models/__init__.py
	# Per-table subscriber classes (type-safe wrappers around generated models).
	run_quietly python /gen_changefeed_subscribers.py \
		--tables component/changefeed/src/isardvdi_changefeed/tables.json \
		--output-dir pkg/gen/asyncapi/changefeed/changefeed_subscribers \
		&& echo "  generated changefeed Python subscribers"
) &
JOB_PIDS="$JOB_PIDS $!"

mkdir -p pkg/oas/apiv4
run_quietly python ./component/apiv4/src/gen_openapi.py --output pkg/oas/apiv4/apiv4.json \
	&& echo "  generated apiv4 OpenAPI spec"

wait_jobs

echo "==> Phase 3: APIv4 clients (Go + TypeScript + Python in parallel)"

(
	set -e
	openapi_go apiv4 pkg/oas/apiv4/apiv4.json pkg/oas/ogen-client.yml
) &
JOB_PIDS="$JOB_PIDS $!"

(
	set -e
	openapi_ts apiv4 || echo "WARNING: openapi_ts apiv4 failed"
) &
JOB_PIDS="$JOB_PIDS $!"

(
	set -e
	openapi_ts_e2e apiv4 || echo "WARNING: openapi_ts_e2e apiv4 failed"
) &
JOB_PIDS="$JOB_PIDS $!"

(
	set -e
	openapi_python isardvdi_apiv4_client pkg/oas/apiv4/apiv4.json
) &
JOB_PIDS="$JOB_PIDS $!"

wait_jobs

rm package.json
rm node_modules

echo "==> Phase 4: Go mocks"
run_quietly mockery && echo "  generated Go mocks"
