ISARDVDI_SRC := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Cap pytest-xdist auto workers so `-n auto` doesn't spawn one worker per core
# on high-core CI runners (= 128 threads → OOM). Override with e.g.
export PYTEST_XDIST_AUTO_NUM_WORKERS ?= 16

.PHONY: all
all: build up test

.PHONY: tidy
tidy:
	go mod tidy

.PHONY: build
build: build-cfg build-compose

.PHONY: build-cfg
build-cfg:
	bash build.sh

.PHONY: build-compose
build-compose:
	docker compose build

.PHONY: pull
pull:
	docker compose pull

.PHONY: up
up:
	@echo Makeup 💄💅💁✨
	docker compose up -d

.PHONY: down
down:
	docker compose down --remove-orphans

.PHONY: reset
reset: down up

.PHONY: lint
lint: lint-python lint-system-deps lint-go lint-frontend lint-old-frontend lint-protobuf lint-alloy

.PHONY: format
format: format-python format-frontend format-old-frontend

.PHONY: lint-python
lint-python:
	uv run isort --check .
	uv run black --check .

.PHONY: format-python
format-python:
	uv run isort .
	uv run black .

.PHONY: lint-system-deps
lint-system-deps:
	uv run python docker/lib/check-system-deps.py

.PHONY: lint-go
lint-go:
	@if command -v golangci-lint >/dev/null 2>&1; then \
		golangci-lint fmt --diff; \
	else \
		go tool -modfile=tools/go.mod golangci-lint fmt --diff; \
	fi

.PHONY: lint-frontend
lint-frontend: lint-frontend-format lint-frontend-lint

.PHONY: lint-frontend-format
lint-frontend-format:
	cd component/frontend && bun install --frozen-lockfile && bun run format --write=false --check

.PHONY: lint-frontend-lint
lint-frontend-lint:
	cd component/frontend && bun install --frozen-lockfile && bun run lint

.PHONY: format-frontend
format-frontend:
	cd component/frontend && bun install --frozen-lockfile && bun run format && bun run lint:fix

.PHONY: lint-old-frontend
lint-old-frontend:
	cd old-frontend && bun install --frozen-lockfile && bun run lint --no-fix --max-warnings 0
	sh old-frontend/tests/no-unsanitized-v-html.sh

.PHONY: format-old-frontend
format-old-frontend:
	cd old-frontend && bun install --frozen-lockfile && bun run lint --fix

.PHONY: lint-protobuf
lint-protobuf:
	buf lint
	buf breaking --against https://gitlab.com/isard/isardvdi.git

.PHONY: lint-alloy
lint-alloy:
	find . -iname "*.alloy" | xargs -n1 alloy fmt -t
	alloy validate docker/grafana-alloy

.PHONY: test
test: test-go test-python test-e2e

.PHONY: test-go
test-go:
	go test -race -cover ./...

# Behavioural unit tests for the vmalert storage-governor rules, under the same
# vmalert engine (MetricsQL) the stack runs. The vmalert-tool version is DERIVED
# from the runtime vmalert pin in docker-compose-parts/monitor.yml, so it cannot
# drift from what the stack runs.
.PHONY: test-vmalert
test-vmalert:
	@VER=$$(grep -oE 'victoriametrics/vmalert:v[0-9.]+' docker-compose-parts/monitor.yml | head -1 | sed 's/.*://'); \
	[ -n "$$VER" ] || { echo "cannot read vmalert pin from docker-compose-parts/monitor.yml"; exit 1; }; \
	docker run --rm -v "$$(pwd)/docker/vmalert/rules:/rules" -w /rules \
	  victoriametrics/vmalert-tool:$$VER unittest --files /rules/storage_governor.test.yml

# Python test matrix — single source of truth for both the dev (`test-*`)
# and CI (`ci-test-*`) targets. One row per workspace package:
#   name : cov-module : dir : pytest-path [: pytest-path...]
# The uv package is always isardvdi-<name>, so it is derived, not a column.
# Both target flavours cd into the same dir, so cov-module resolves
# identically for the dev and the CI run. Every field after the third is a
# pytest path, so a package whose suites live in two trees lists both.
# Dev targets run with the dev group; CI targets run --no-dev (prod + test).
# Every Python workspace suite is generated from this table. The suites that
# are not workspace packages keep their own targets: test-go/ci-test-go,
# ci-test-frontend (bun), test-engine (runs inside the container), test-e2e,
# test-vmalert, test-sparsify and ci-test-storage-utils.
PY_PKGS := \
	apiv4:api:component/apiv4/src:api/ \
	common:isardvdi_common:component/_common/src:isardvdi_common \
	change-handler:isardvdi_change_handler:component/change-handler/src:isardvdi_change_handler/tests/ \
	changefeed:isardvdi_changefeed:component/changefeed/src:isardvdi_changefeed/tests/ \
	socketio:isardvdi_socketio:component/socketio/src:isardvdi_socketio/tests \
	openapi:isardvdi_openapi:component/openapi/src:isardvdi_openapi/tests \
	notifier:notifier:notifier:tests \
	scheduler:scheduler:scheduler:tests \
	webapp:webapp:webapp/webapp:tests \
	apiv4-client:isardvdi_apiv4_client_auth:component/_common/isardvdi_apiv4_client:tests \
	vpn:src:docker/vpn:tests \
	storage:task:docker/storage:task/tests:utils/tests \
	codegen:.:docker/codegen:tests \
	anonymize-db:anonymize_db:sysadm/anonymize-db:tests \
	backupninja:.:docker/backupninja:tests \
	hypervisor:lib:docker/hypervisor/src:.

# Just the short names, in PY_PKGS order — drives the aggregate prereq lists.
PY_PKG_NAMES := $(foreach r,$(PY_PKGS),$(word 1,$(subst :, ,$(r))))

# $1 = whitespace-split row: word 1=name 2=cov-mod 3=dir 4..=pytest-path(s)
define TEST_RULE
.PHONY: test-$(word 1,$1)
test-$(word 1,$1):
	cd $(word 3,$1) && uv run --group test --package isardvdi-$(word 1,$1) pytest $(wordlist 4,$(words $1),$1) -n auto --cov=$(word 2,$1)
endef
$(foreach r,$(PY_PKGS),$(eval $(call TEST_RULE,$(subst :, ,$(r)))))

.PHONY: test-python
test-python: $(addprefix test-,$(PY_PKG_NAMES))

# Mirrors the unit-test-engine CI job: same paths, same two invocations.
# engine/services/db needs importlib mode (see .gitlab-ci.yml for why).
.PHONY: test-engine
test-engine:
	docker exec isard-engine sh -c "cd /isard && python3 -m pytest engine/models engine/controllers engine/services/threads engine/services/lib initdb -v --tb=short"
	docker exec isard-engine sh -c "cd /isard && python3 -m pytest --import-mode=importlib engine/services/db -v --tb=short"

_e2e_tty := $(if $(CI),,-it)

# Usage:
#   make test-e2e                                          # run all specs
#   make test-e2e E2E_ARGS=tests/webapp/login.spec.js      # single spec
#   make test-e2e E2E_ARGS='tests/vue2/'                   # one directory
#   make test-e2e E2E_ARGS='--grep "should login"'         # by test name
.PHONY: test-e2e-seed
test-e2e-seed:
	docker run $(_e2e_tty) --rm \
	--network=isard-network \
	--volumes-from isard-storage \
	-e RETHINKDB_HOST=isard-db \
	-e UV_PROJECT_ENVIRONMENT=/tmp/.venv \
	-e UV_CACHE_DIR=/tmp/uv-cache \
	-v "${ISARDVDI_SRC}:/src" -w /src \
	ghcr.io/astral-sh/uv:0.11.23-python3.14-alpine \
	sh -c 'apk add --no-cache git && uv run --group test --package isardvdi-testing python3 testing/db/populate_test_db.py'

.PHONY: test-e2e
test-e2e: test-e2e-seed
	cd ${ISARDVDI_SRC}/testing/e2e && bun ci
	docker run $(_e2e_tty) \
	--rm --ipc=host \
	--network=isard-network \
	-e DOCKER=1 \
	-e CI \
	-e E2E_WORKERS \
	-e E2E_RETRIES \
	-e E2E_SCREENSHOT \
	-e E2E_TRACE \
	-e E2E_TIMEOUT \
	-e E2E_BASE_URL=$${E2E_BASE_URL:-https://isard-portal} \
	-e E2E_REPORTER \
	-e E2E_VIDEO \
	-e E2E_BROWSER \
	-v "${ISARDVDI_SRC}/testing/e2e:/e2e" \
	-w "/e2e" \
	mcr.microsoft.com/playwright:v1.57.0-jammy yarn playwright test $(E2E_ARGS)

# Recovery-trap suite for docker/storage/utils/sparsify. Pure bash, but it needs
# real qcow2 images and a live lock holder, so qemu-img and qemu-io must exist.
.PHONY: test-sparsify
test-sparsify:
	bash docker/storage/utils/tests/test_sparsify_recover_backup.sh

# Regression test for the `storage` cleanup CLI's sparsify-backup classifier:
# a locked/in-use canonical must keep its backup, because the lock-bypassing
# check reads through the lock and calls a half-written image clean. The CLI is
# loaded by path (no .py suffix) and its qemu-img calls are replaced, so this
# needs no qemu binaries and no lock holder.
.PHONY: ci-test-storage-utils
ci-test-storage-utils:
	uv sync --no-dev --group test --package isardvdi-storage
	cd docker/storage/utils && uv run --no-dev --group test --package isardvdi-storage pytest tests/test_classify_sparsify_backup.py -q --tb=short --junitxml=report.xml


# CI test targets: emit JUnit + Cobertura XML so GitLab CI can consume them
# via artifacts.reports.*. Paths must match .gitlab-ci.yml byte-identical.

.PHONY: ci-test-go
ci-test-go:
	go tool -modfile=tools/go.mod gotestsum --junitfile report.xml --format testname -- -race ./... -coverprofile coverage.out -covermode atomic
	go tool cover -func coverage.out
	go tool -modfile=tools/go.mod gocover-cobertura -ignore-gen-files < coverage.out > coverage.xml

# ci-test-* targets generated from PY_PKGS (the matrix above), except the two
# whose suites assert on a real Redis: they run under docker/lib/ci-with-redis.sh
# and declare a skip-count gate, which the generated recipe cannot express, so
# they stay written out below.
# apiv4 needs USAGE=production at runtime; that comes from the CI job's
# `variables:` block (.gitlab-ci.yml unit-test-apiv4), not inline here.
CI_TEST_GENERATED := $(filter-out common change-handler,$(PY_PKG_NAMES))

define CI_TEST_RULE
.PHONY: ci-test-$(word 1,$1)
ci-test-$(word 1,$1):
	uv sync --no-dev --group test --package isardvdi-$(word 1,$1)
	cd $(word 3,$1) && uv run --no-dev --group test --package isardvdi-$(word 1,$1) pytest $(wordlist 4,$(words $1),$1) -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=$(word 2,$1) --cov-report=term --cov-report=xml:coverage.xml
endef
$(foreach r,$(PY_PKGS),\
  $(if $(filter $(word 1,$(subst :, ,$(r))),$(CI_TEST_GENERATED)),\
    $(eval $(call CI_TEST_RULE,$(subst :, ,$(r))))))

# Contract suites: what a third-party dependency really does, proved against it.
# Needs only that dependency, never the stack, so it does not belong in a unit
# job and does not need the compose file the rest of testing/integration wants.
.PHONY: ci-test-contracts
ci-test-contracts:
	uv sync --no-dev --group test --package isardvdi-testing
	docker/lib/ci-with-redis.sh sh -c 'uv run --no-dev --group test --package isardvdi-testing pytest testing/integration/contracts -q --tb=short --junitxml=testing/integration/contracts/report.xml'

.PHONY: ci-test-common
ci-test-common:
	uv sync --no-dev --group test --package isardvdi-common --package isardvdi-apiv4 --package isardvdi-change-handler --package isardvdi-socketio
	SKIP_GATE_REPORT=component/_common/src/report.xml docker/lib/ci-with-redis.sh sh -c 'cd component/_common/src && uv run --no-dev --group test --package isardvdi-common pytest isardvdi_common -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_common --cov-report=term --cov-report=xml:coverage.xml'

.PHONY: ci-test-change-handler
ci-test-change-handler:
	uv sync --no-dev --group test --package isardvdi-change-handler
	SKIP_GATE_REPORT=component/change-handler/src/report.xml docker/lib/ci-with-redis.sh sh -c 'cd component/change-handler/src && uv run --no-dev --group test --package isardvdi-change-handler pytest isardvdi_change_handler/tests/ -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_change_handler --cov-report=term --cov-report=xml:coverage.xml'

.PHONY: ci-test-frontend
ci-test-frontend:
	cd component/frontend && bun install --frozen-lockfile && bun run test:unit --reporter=default --reporter=junit --outputFile=report.xml

.PHONY: ci-test-webapp-js
ci-test-webapp-js:
	for t in webapp/webapp/webapp/static/admin/js/tests/*.test.js; do echo "== $$t"; bun "$$t" || exit 1; done

.PHONY: ci-test-python
ci-test-python: $(addprefix ci-test-,$(PY_PKG_NAMES))

.PHONY: setup-hooks
setup-hooks:
	git config core.hooksPath .githooks
	@echo "Git hooks installed from .githooks/"

.PHONY: ci-lint
ci-lint: lint

.PHONY: ci-test
ci-test: ci-test-go ci-test-python

.PHONY: ci-fix
ci-fix: format

.PHONY: ci-e2e
ci-e2e: test-e2e-seed test-e2e

# Builds+runs the isolated e2e stack that mirrors .gitlab-ci.yml's
# test-e2e job (CI == local guarantee). Because both stacks share
# container names (isard-portal, isard-db, …) the dev stack must
# be DOWN before this target runs. Use `make test-e2e-stack-restore`
# to bring the dev stack back afterwards.
#
# Prereq: run `make down` first to stop the dev stack.
.PHONY: test-e2e-stack
test-e2e-stack:
	@if docker ps --format '{{.Names}}' | grep -q '^isard-portal$$'; then \
		echo "❌ Dev stack is up. Run 'make down' first, then retry."; \
		exit 1; \
	fi
	@echo "🎭 Generating isardvdi.e2e.cfg from cfg.example + e2e template…"
	cp ${ISARDVDI_SRC}isardvdi.cfg.example ${ISARDVDI_SRC}isardvdi.e2e.cfg
	cat ${ISARDVDI_SRC}testing/config/isardvdi.e2e.cfg.template >> ${ISARDVDI_SRC}isardvdi.e2e.cfg
	@# Inherit dev stack's image prefix+tag so we reuse already-built images.
	@DEV_PREFIX=$$(grep -E '^DOCKER_IMAGE_PREFIX=' ${ISARDVDI_SRC}isardvdi.cfg | cut -d= -f2-) && \
	DEV_TAG=$$(grep -E '^DOCKER_IMAGE_TAG=' ${ISARDVDI_SRC}isardvdi.cfg | cut -d= -f2-) && \
	echo "DOCKER_IMAGE_PREFIX=$$DEV_PREFIX" >> ${ISARDVDI_SRC}isardvdi.e2e.cfg && \
	echo "DOCKER_IMAGE_TAG=$$DEV_TAG" >> ${ISARDVDI_SRC}isardvdi.e2e.cfg && \
	echo "📌 Pinned to $$DEV_PREFIX*:$$DEV_TAG"
	CODEGEN=false bash ${ISARDVDI_SRC}build.sh
	@echo "🚢 Bringing up e2e stack (reusing local images)…"
	docker compose -f docker-compose.e2e.yml up -d
	@echo "⏳ Waiting for stack…"
	bash ${ISARDVDI_SRC}testing/integration/wait-for-stack.sh 240 || true
	$(MAKE) test-e2e-seed
	@echo "🧪 Running Playwright…"
	cd ${ISARDVDI_SRC}testing/e2e && yarn install --frozen-lockfile
	PORTAL_IP="$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' isard-portal | tr -d '\n')" && \
	NETWORK_ID="$$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}' isard-portal | tr -d '\n')" && \
	docker run --rm --ipc=host \
		--network="$$NETWORK_ID" \
		--add-host="host.docker.internal:$$PORTAL_IP" \
		-e DOCKER=1 -e CI=1 \
		-e E2E_WORKERS=2 -e E2E_RETRIES=2 \
		-e E2E_SCREENSHOT=only-on-failure \
		-e E2E_TRACE=on-first-retry \
		-e E2E_BASE_URL=https://host.docker.internal \
		-e E2E_RATE_LIMITS_ENABLED=false \
		-v "${ISARDVDI_SRC}testing/e2e:/e2e" -w "/e2e" \
		mcr.microsoft.com/playwright:v1.57.0-jammy \
		yarn playwright test $(E2E_ARGS)

.PHONY: test-e2e-stack-down
test-e2e-stack-down:
	-docker compose -f docker-compose.e2e.yml down --remove-orphans
	-rm -f ${ISARDVDI_SRC}isardvdi.e2e.cfg ${ISARDVDI_SRC}docker-compose.e2e.yml

# Run the Vue 2 (old-frontend) Playwright suite against the
# currently-running stack. ``BASE_URL`` defaults to https://localhost
# matching ``old-frontend/playwright.config.js``. The suite expects:
#   * Stack running with images current to the branch — ``make build &&
#     make up`` if you've added/changed Vue 2 or apiv4 since last bring-up.
#   * Seed templates available — typically by restoring an anon dump
#     (``/opt/load-testing/scripts/restore-dump.sh``) plus running
#     ``/opt/load-testing/scripts/seed-fixtures.py``.
# Specs that need template fixtures will ``test.skip(...)`` cleanly
# rather than fail when the stack is empty.
# Reproducible regression gate (default mode).
# * 1 worker — eliminates parallel races on a single-instance stack.
# * 2 retries — flakes classified as "flaky", true regressions
#   surface as a real failure.
# * Auto-seeded admin pool isolates sessions across runs.
#
# Usage:
#   make test-e2e-old-frontend                  # serial, retries on
#   make test-e2e-old-frontend E2E_ARGS='--grep="Bug #47"'
#
# For parallel iteration mode, use the ``-parallel`` target below.
.PHONY: test-e2e-old-frontend
test-e2e-old-frontend:
	cd ${ISARDVDI_SRC}old-frontend && bun install --frozen-lockfile
	cd ${ISARDVDI_SRC}old-frontend && \
		E2E_ADMIN_USERNAME=$${E2E_ADMIN_USERNAME:-admin} \
		E2E_ADMIN_PASSWORD=$${E2E_ADMIN_PASSWORD:-IsardVDI} \
		E2E_WORKERS=1 \
		E2E_RETRIES=$${E2E_RETRIES:-2} \
		bun run test:e2e $(E2E_ARGS)

# Fast parallel mode — opt-in. Useful for "did my fix touch these
# specific tests" iteration, NOT for regression gating: parallel
# may flake transiently on this dev stack.
#
# Usage:
#   make test-e2e-old-frontend-parallel                  # auto worker count
#   make test-e2e-old-frontend-parallel E2E_WORKERS=8    # explicit
.PHONY: test-e2e-old-frontend-parallel
test-e2e-old-frontend-parallel:
	cd ${ISARDVDI_SRC}old-frontend && bun install --frozen-lockfile
	cd ${ISARDVDI_SRC}old-frontend && \
		E2E_ADMIN_USERNAME=$${E2E_ADMIN_USERNAME:-admin} \
		E2E_ADMIN_PASSWORD=$${E2E_ADMIN_PASSWORD:-IsardVDI} \
		E2E_WORKERS=$${E2E_WORKERS:-4} \
		E2E_RETRIES=$${E2E_RETRIES:-2} \
		bun run test:e2e $(E2E_ARGS)

# Single-spec convenience: ``make test-e2e-old-frontend-spec
# SPEC=tests/e2e/vue2-coowner-modal.spec.js``. Useful when iterating
# on a regression test against a known-bad stack.
.PHONY: test-e2e-old-frontend-spec
test-e2e-old-frontend-spec:
	@if [ -z "$(SPEC)" ]; then echo "usage: make test-e2e-old-frontend-spec SPEC=tests/e2e/<file>.spec.js"; exit 2; fi
	cd ${ISARDVDI_SRC}old-frontend && bun install --frozen-lockfile
	cd ${ISARDVDI_SRC}old-frontend && bun run test:e2e -- --project=chromium $(SPEC)

# Convenience: tears down e2e stack, removes generated artefacts,
# and brings dev stack back up from isardvdi.cfg.
.PHONY: test-e2e-stack-restore
test-e2e-stack-restore: test-e2e-stack-down up

.PHONY: ci
ci: ci-lint ci-test

.PHONY: ci-all
ci-all: ci ci-e2e

.PHONY: ci-fix-and-test
ci-fix-and-test: ci-fix ci-lint ci-test

.PHONY: shell
shell:
	docker exec -it ${CONTAINER} /bin/ash

.PHONY: shell-user
shell-user:
	docker exec -u "$$(id -u):$$(id -g)" -it ${CONTAINER} /bin/ash
