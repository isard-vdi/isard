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
rm -rf component/frontend/src/gen
rm -f ./*/**/testing_*_mock.go

mkdir -p /tmp/go /tmp/go-cache
export HOME=/tmp
export GOPATH=/tmp/go
export GOCACHE=/tmp/go-cache

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
openapi_ts authentication || echo "WARNING: openapi_ts authentication failed"

# APIv4 OAS
source /apiv4-venv/bin/activate
export PYTHONPATH=${PYTHONPATH}:/build/pkg/gen/proto/python
mkdir -p pkg/oas/apiv4
python ./component/apiv4/src/gen_openapi.py --output pkg/oas/apiv4/apiv4.json

mkdir -p pkg/gen/oas/apiv4
ogen --target ./pkg/gen/oas/apiv4 -package apiv4 --clean --config pkg/oas/apiv4/ogen.yml pkg/oas/apiv4/apiv4.json
openapi_ts apiv4 || echo "WARNING: openapi_ts apiv4 failed"

# Changefeed AsyncAPI (spec + Pydantic models)
mkdir -p pkg/gen/asyncapi/changefeed
python /gen_changefeed_asyncapi.py \
	--tables component/changefeed/src/tables.json \
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
	--tables component/changefeed/src/tables.json \
	--output-dir pkg/gen/asyncapi/changefeed/changefeed_subscribers

# Go mocks
mockery
cd pkg/sdk && mockery && cd -
