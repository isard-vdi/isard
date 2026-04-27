#!/bin/sh

set -e

openapi_go() {
	# $1 = api name (also package + target dir under pkg/gen/oas/)
	# $2 = path to OpenAPI JSON spec
	# $3 = optional path to ogen config file
	mkdir -p "pkg/gen/oas/$1"
	if [ -n "$3" ]; then
		ogen --target "./pkg/gen/oas/$1" -package "$1" --clean --config "$3" "$2"
	else
		ogen --target "./pkg/gen/oas/$1" -package "$1" --clean "$2"
	fi
}

openapi_ts() {
	ln -s /deps/package.json .
	ln -s /deps/node_modules .

	CODEGEN="$1" npx --no @hey-api/openapi-ts

	rm package.json
	rm node_modules
}

openapi_python() {
	# $1 = client package dir name (e.g. isardvdi_apiv4_client)
	# $2 = path to OpenAPI JSON spec
	# openapi-python-client lives in the unified workspace venv (/venv ->
	# /workspace/.venv) installed via docker/codegen/pyproject.toml deps.
	openapi-python-client generate \
		--path "$2" \
		--output-path "component/_common/$1/src/$1" \
		--overwrite \
		--config "component/_common/$1/openapi-python-client.yml" \
		--meta=none
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
rm -rf component/_common/isardvdi_apiv4_client/src/isardvdi_apiv4_client
rm -rf component/_common/isardvdi_authentication_client/src/isardvdi_authentication_client
rm -rf component/_common/isardvdi_notifier_client/src/isardvdi_notifier_client
rm -rf component/_common/isardvdi_scheduler_client/src/isardvdi_scheduler_client
rm -f ./*/**/testing_*_mock.go

mkdir -p /tmp/go /tmp/go-cache
export HOME=/tmp
export GOPATH=/tmp/go
export GOCACHE=/tmp/go-cache

# Silence noise from transitive deps of @asyncapi/cli:
#   - node-config "No configurations found" warning (env var)
#   - node-config strict-mode warning (NODE_ENV=production with no matching
#     file). _warnOrThrow has no env escape, so we point NODE_CONFIG_DIR at a
#     scratch dir holding empty production.json + development.json instead.
#   - punycode is a Node stdlib deprecation surfaced by an asyncapi sub-dep
#   - CI=true makes the asyncapi CLI skip analytics + the tracking notice in a
#     single env var, with no config file to write (see base.js recorderFromEnv)
export SUPPRESS_NO_CONFIG_WARNING=true
export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--no-deprecation"
export CI=true
export NODE_CONFIG_DIR=/tmp/node-config-shim
mkdir -p "$NODE_CONFIG_DIR"
echo '{}' > "$NODE_CONFIG_DIR/production.json"
echo '{}' > "$NODE_CONFIG_DIR/development.json"

# Protobuf
source /venv/bin/activate
if [ -n "${BUF_TOKEN:+x}" ] && [ -n "$BUF_TOKEN" ]; then
  echo "Found buf token, authenticating with buf.build to avoid rate limits"
  export BUF_TOKEN
else
  echo "No buf token found, we may hit rate limits"
  unset BUF_TOKEN
fi
# Retry buf generate on transient BSR failures (deadline_exceeded,
# resource_exhausted). Backoff is long because anonymous BSR rate-limits
# reset on the order of a minute, not seconds.
buf_attempts=0
buf_backoff=30
until buf generate; do
  buf_attempts=$((buf_attempts + 1))
  if [ "$buf_attempts" -ge 3 ]; then
    echo "buf generate failed after $buf_attempts attempts (consider setting BUF_TOKEN)" >&2
    exit 1
  fi
  echo "buf generate failed (attempt $buf_attempts/3), retrying in ${buf_backoff}s..." >&2
  sleep "$buf_backoff"
  buf_backoff=$((buf_backoff * 2))
done

# Mark isardvdi_protobuf as a package so the src-layout wheel can import it.
touch pkg/gen/proto/python/src/isardvdi_protobuf/__init__.py

# Rewrite bare sibling imports in generated grpcio *_pb2_grpc.py files to use
# the isardvdi_protobuf. package prefix, so they resolve after src-layout packaging.
python3 -c "
import re, pathlib
grpc_dir = pathlib.Path('pkg/gen/proto/python/src/isardvdi_protobuf')
for f in grpc_dir.rglob('*_pb2_grpc.py'):
    text = f.read_text()
    # Replace: from <pkg>.v1 import <pkg>_pb2  ->  from isardvdi_protobuf.<pkg>.v1 import <pkg>_pb2
    new_text = re.sub(r'^(from )([a-z_]+)(\.v\d+ import \S+)', r'\1isardvdi_protobuf.\2\3', text, flags=re.MULTILINE)
    if new_text != text:
        f.write_text(new_text)
        print(f'  rewritten: {f}')
"

# Notifier
openapi_go notifier pkg/oas/notifier/notifier.json
openapi_python isardvdi_notifier_client pkg/oas/notifier/notifier.json

# Scheduler
openapi_go scheduler pkg/oas/scheduler/scheduler.json pkg/oas/scheduler/ogen.yml
openapi_python isardvdi_scheduler_client pkg/oas/scheduler/scheduler.json

# Authentication (Python client must exist before gen_openapi.py runs,
# since apiv4's services/migrations.py imports isardvdi_authentication_client
# at module level).
openapi_go authentication pkg/oas/authentication/authentication.json
openapi_ts authentication || echo "WARNING: openapi_ts authentication failed"
openapi_python isardvdi_authentication_client pkg/oas/authentication/authentication.json

# APIv4 OAS
source /apiv4-venv/bin/activate
# Workspace install at image build time only saw the stub __init__.py for the
# four generated clients (chicken-and-egg: codegen output is gitignored). Add
# the freshly generated src/ dirs to PYTHONPATH so they take precedence over
# the empty stubs installed in the venv.
export PYTHONPATH=/build/component/_common/isardvdi_authentication_client/src:/build/component/_common/isardvdi_notifier_client/src:/build/component/_common/isardvdi_scheduler_client/src:/build/pkg/gen/proto/python/src${PYTHONPATH:+:$PYTHONPATH}
mkdir -p pkg/oas/apiv4
python ./component/apiv4/src/gen_openapi.py --output pkg/oas/apiv4/apiv4.json

# APIv4
openapi_go apiv4 pkg/oas/apiv4/apiv4.json pkg/oas/apiv4/ogen.yml
openapi_ts apiv4 || echo "WARNING: openapi_ts apiv4 failed"
openapi_python isardvdi_apiv4_client pkg/oas/apiv4/apiv4.json

# Changefeed AsyncAPI (spec + Pydantic models)
source /apiv4-venv/bin/activate
mkdir -p pkg/gen/asyncapi/changefeed
python /gen_changefeed_asyncapi.py \
	--tables component/changefeed/src/isardvdi_changefeed/tables.json \
	--output pkg/gen/asyncapi/changefeed/changefeed.yaml

# oclif (used by the asyncapi CLI) falls back to os.userInfo() when $SHELL is
# unset, which calls getpwuid() and fails under an arbitrary runtime UID with
# no /etc/passwd entry. $HOME is already exported at the top of this script,
# so os.homedir() is also safe.
export SHELL=/bin/sh

ln -sf /deps/package.json .
ln -sf /deps/node_modules .
npx --no asyncapi validate pkg/gen/asyncapi/changefeed/changefeed.yaml
# Generate into a directory matching --packageName so that
# ``from changefeed_models.domains_change import DomainsChange`` works
# once ``pkg/gen/asyncapi/changefeed`` is on PYTHONPATH.
npx --no asyncapi generate models python \
	pkg/gen/asyncapi/changefeed/changefeed.yaml \
	-o pkg/gen/asyncapi/changefeed/changefeed_models \
	--packageName=changefeed_models \
	--pyDantic
touch pkg/gen/asyncapi/changefeed/changefeed_models/__init__.py
rm package.json
rm node_modules

# Per-table subscriber classes (type-safe wrappers around generated models)
python /gen_changefeed_subscribers.py \
	--tables component/changefeed/src/isardvdi_changefeed/tables.json \
	--output-dir pkg/gen/asyncapi/changefeed/changefeed_subscribers

# Go mocks
mockery
