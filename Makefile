ISARDVDI_SRC := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

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
lint: lint-python lint-system-deps lint-go lint-frontend lint-old-frontend lint-protobuf

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
	golangci-lint fmt --diff

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

.PHONY: test
test: test-go test-python test-e2e

.PHONY: test-go
test-go:
	go test -race -cover ./...

.PHONY: test-python
test-python: test-apiv4 test-common test-change-handler test-changefeed test-socketio test-core-worker test-openapi test-notifier test-scheduler test-webapp

.PHONY: test-python-cov
test-python-cov:
	$(MAKE) PYTEST_COV_ARGS='__COV__' test-python
	@echo "HTML coverage under component/*/src/htmlcov/"

# Internal: if PYTEST_COV_ARGS is set to the sentinel, expand to per-package coverage flags.
# Otherwise it's empty (fast default).
_apiv4_cov := $(if $(filter __COV__,$(PYTEST_COV_ARGS)),--cov=api --cov-report=html:component/apiv4/src/htmlcov,)
_common_cov := $(if $(filter __COV__,$(PYTEST_COV_ARGS)),--cov=isardvdi_common --cov-report=html:component/_common/src/htmlcov,)
_chandler_cov := $(if $(filter __COV__,$(PYTEST_COV_ARGS)),--cov=isardvdi_change_handler --cov-report=html:component/change-handler/src/htmlcov,)
_cfeed_cov := $(if $(filter __COV__,$(PYTEST_COV_ARGS)),--cov=isardvdi_changefeed --cov-report=html:component/changefeed/src/htmlcov,)

.PHONY: test-engine
test-engine:
	docker exec isard-engine sh -c "cd /isard && python3 -m pytest engine/models engine/services/threads -v --tb=short"

.PHONY: test-e2e-seed
test-e2e-seed:
	uv run --group test --package isardvdi-testing python3 testing/db/populate_test_db.py

.PHONY: test-e2e
test-e2e: test-e2e-seed
	cd ${ISARDVDI_SRC}/testing/e2e && yarn
	docker run -it \
	--rm --ipc=host \
	--network=host \
	--add-host=host.docker.internal:host-gateway \
	-e DOCKER=1 \
	-e CI \
	-e E2E_WORKERS \
	-e E2E_RETRIES \
	-e E2E_SCREENSHOT \
	-e E2E_TRACE \
	-e E2E_TIMEOUT \
	-e E2E_BASE_URL \
	-e E2E_REPORTER \
	-e E2E_VIDEO \
	-e E2E_BROWSER \
	-v "${ISARDVDI_SRC}/testing/e2e:/e2e" \
	-w "/e2e" \
	mcr.microsoft.com/playwright:v1.57.0-jammy yarn playwright test

.PHONY: test-apiv4
test-apiv4:
	uv run --group test --package isardvdi-apiv4 pytest component/apiv4/src -n auto $(_apiv4_cov)

.PHONY: test-common
test-common:
	uv run --group test --package isardvdi-common pytest component/_common/src/isardvdi_common -n auto $(_common_cov)

.PHONY: test-change-handler
test-change-handler:
	uv run --group test --package isardvdi-change-handler pytest component/change-handler/src/isardvdi_change_handler/tests -n auto $(_chandler_cov)

.PHONY: test-changefeed
test-changefeed:
	uv run --group test --package isardvdi-changefeed pytest component/changefeed/src/isardvdi_changefeed/tests -n auto $(_cfeed_cov)

.PHONY: test-socketio
test-socketio:
	uv run --group test --package isardvdi-socketio pytest component/socketio/src/isardvdi_socketio/tests -n auto

.PHONY: test-core-worker
test-core-worker:
	uv run --group test --package isardvdi-core-worker pytest component/core_worker/src/isardvdi_core_worker/tests -n auto

.PHONY: test-openapi
test-openapi:
	uv run --group test --package isardvdi-openapi pytest component/openapi/src/isardvdi_openapi/tests -n auto

.PHONY: test-notifier
test-notifier:
	uv run --group test --package isardvdi-notifier pytest notifier/tests -n auto

.PHONY: test-scheduler
test-scheduler:
	uv run --group test --package isardvdi-scheduler pytest scheduler/tests -n auto

.PHONY: test-webapp
test-webapp:
	uv sync --no-dev --group test --package isardvdi-webapp
	uv run --no-dev --group test --package isardvdi-webapp pytest webapp/webapp/tests -n auto

# CI test targets: emit JUnit + Cobertura XML so GitLab CI can consume them
# via artifacts.reports.*. Paths must match .gitlab-ci.yml byte-identical.

.PHONY: ci-test-go
ci-test-go:
	@command -v gotestsum >/dev/null 2>&1 || { echo "gotestsum not found. Install with: go install gotest.tools/gotestsum@latest"; exit 1; }
	@command -v gocover-cobertura >/dev/null 2>&1 || { echo "gocover-cobertura not found. Install with: go install github.com/boumenot/gocover-cobertura@latest"; exit 1; }
	gotestsum --junitfile report.xml --format testname -- -race ./... -coverprofile coverage.out -covermode atomic
	go tool cover -func coverage.out
	gocover-cobertura -ignore-gen-files < coverage.out > coverage.xml

.PHONY: ci-test-apiv4
ci-test-apiv4:
	uv sync --no-dev --group test --package isardvdi-apiv4
	cd component/apiv4/src && USAGE=$${USAGE:-production} uv run --no-dev --group test --package isardvdi-apiv4 pytest api/ -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=api --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-common
ci-test-common:
	uv sync --no-dev --group test --package isardvdi-common --package isardvdi-apiv4 --package isardvdi-change-handler --package isardvdi-socketio
	cd component/_common/src && uv run --no-dev --group test --package isardvdi-common pytest isardvdi_common -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_common --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-change-handler
ci-test-change-handler:
	uv sync --no-dev --group test --package isardvdi-change-handler
	cd component/change-handler/src && uv run --no-dev --group test --package isardvdi-change-handler pytest isardvdi_change_handler/tests/ -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_change_handler --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-changefeed
ci-test-changefeed:
	uv sync --no-dev --group test --package isardvdi-changefeed
	cd component/changefeed/src && uv run --no-dev --group test --package isardvdi-changefeed pytest isardvdi_changefeed/tests/ -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_changefeed --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-socketio
ci-test-socketio:
	uv sync --no-dev --group test --package isardvdi-socketio
	cd component/socketio/src && uv run --no-dev --group test --package isardvdi-socketio pytest isardvdi_socketio/tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_socketio --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-core-worker
ci-test-core-worker:
	uv sync --no-dev --group test --package isardvdi-core-worker
	cd component/core_worker/src && uv run --no-dev --group test --package isardvdi-core-worker pytest isardvdi_core_worker/tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_core_worker --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-openapi
ci-test-openapi:
	uv sync --no-dev --group test --package isardvdi-openapi
	cd component/openapi/src && uv run --no-dev --group test --package isardvdi-openapi pytest isardvdi_openapi/tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=isardvdi_openapi --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-notifier
ci-test-notifier:
	uv sync --no-dev --group test --package isardvdi-notifier
	cd notifier && uv run --no-dev --group test --package isardvdi-notifier pytest tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=notifier --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-scheduler
ci-test-scheduler:
	uv sync --no-dev --group test --package isardvdi-scheduler
	cd scheduler && uv run --no-dev --group test --package isardvdi-scheduler pytest tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=scheduler --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-webapp
ci-test-webapp:
	uv sync --no-dev --group test --package isardvdi-webapp
	cd webapp/webapp && uv run --no-dev --group test --package isardvdi-webapp pytest tests -q -n auto --dist=loadfile --tb=short --junitxml=report.xml --cov=webapp --cov-report=term --cov-report=xml:coverage.xml

.PHONY: ci-test-python
ci-test-python: ci-test-apiv4 ci-test-common ci-test-change-handler ci-test-changefeed ci-test-socketio ci-test-core-worker ci-test-openapi ci-test-notifier ci-test-scheduler ci-test-webapp

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
	@echo "🎭 Generating isardvdi.e2e.cfg from template…"
	cp ${ISARDVDI_SRC}testing/config/isardvdi.e2e.cfg.template ${ISARDVDI_SRC}isardvdi.e2e.cfg
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
		yarn playwright test

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
# Usage:
#   make test-e2e-old-frontend                  # Playwright auto-picks worker count
#   make test-e2e-old-frontend E2E_WORKERS=8    # 8 parallel workers
#   make test-e2e-old-frontend E2E_WORKERS=1    # serial
#   make test-e2e-old-frontend E2E_ARGS='--grep="Bug #47"'
#
# A pool of admin users is seeded once at suite start (one per
# worker) and removed after. The pool keeps each worker's session
# isolated in isard-sessions, so any worker count is safe.
.PHONY: test-e2e-old-frontend
test-e2e-old-frontend:
	cd ${ISARDVDI_SRC}old-frontend && bun install --frozen-lockfile
	cd ${ISARDVDI_SRC}old-frontend && \
		E2E_ADMIN_USERNAME=$${E2E_ADMIN_USERNAME:-admin} \
		E2E_ADMIN_PASSWORD=$${E2E_ADMIN_PASSWORD:-IsardVDI} \
		E2E_WORKERS=$${E2E_WORKERS:-} \
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
