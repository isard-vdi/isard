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

.PHONY: test
test: test-go test-e2e test-apiv4

.PHONY: test-go
test-go:
	go test -race -cover ./...

.PHONY: test-engine
test-engine:
	docker exec isard-engine sh -c "pip install -q --break-system-packages pytest >/dev/null 2>&1 || true; cd /isard && python3 -m pytest engine/models engine/services/threads -v --tb=short"

.PHONY: test-e2e-seed
test-e2e-seed:
	pip install rethinkdb 2>/dev/null || pip install --break-system-packages rethinkdb
	python3 testing/db/populate_test_db.py

.PHONY: test-e2e
test-e2e: test-e2e-seed
	cd ${ISARDVDI_SRC}/testing/e2e && yarn
	docker run -it \
	--rm --ipc=host \
	--network=host \
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
	docker exec -it isard-apiv4 pip install -r /test.requirements.txt
	@echo "Installing rethinkdb-mock fork..."
	-docker exec -it -u root isard-apiv4 bash -c "\
		apt update && \
		apt install -y git && \
		git clone -b core-document-manipulation \
			https://github.com/isard-vdi/rethinkdb-mock.git /rethinkdb-mock && \
		pip install /rethinkdb-mock \
	"
	docker exec -it isard-apiv4 pytest /app --cov=/app --cov-report=html
	@echo "HTML coverage report at ${ISARDVDI_SRC}component/apiv4/src/htmlcov/index.html"

.PHONY: setup-hooks
setup-hooks:
	git config core.hooksPath .githooks
	@echo "Git hooks installed from .githooks/"

.PHONY: ci-lint
ci-lint:
	docker compose -f docker-compose.ci.yml --profile lint up --abort-on-container-exit

.PHONY: ci-test
ci-test:
	docker compose -f docker-compose.ci.yml run --rm check-codegen-freshness
	docker compose -f docker-compose.ci.yml run --rm unit-test-apiv4
	docker compose -f docker-compose.ci.yml run --rm unit-test-webapp
	docker compose -f docker-compose.ci.yml run --rm unit-test-go

.PHONY: ci-test-webapp
ci-test-webapp:
	docker compose -f docker-compose.ci.yml run --rm unit-test-webapp

.PHONY: ci-fix
ci-fix:
	docker compose -f docker-compose.ci.yml --profile fix up

.PHONY: ci-integration-test
ci-integration-test:
	docker compose -f docker-compose.ci.yml run --rm integration-test-change-handler
	docker compose -f docker-compose.ci.yml run --rm integration-test-changefeed
	docker compose -f docker-compose.ci.yml run --rm integration-test-common
	docker compose -f docker-compose.ci.yml run --rm integration-test-apiv4

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

# Convenience: tears down e2e stack, removes generated artefacts,
# and brings dev stack back up from isardvdi.cfg.
.PHONY: test-e2e-stack-restore
test-e2e-stack-restore: test-e2e-stack-down up

.PHONY: ci
ci: ci-lint ci-test ci-integration-test

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
