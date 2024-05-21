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
	docker compose up -d

.PHONY: down
down:
	docker compose down --remove-orphans

.PHONY: reset
reset: down up

.PHONY: test
test: test-go test-e2e

.PHONY: test-go
test-go:
	go test -race -cover ./...

.PHONY: test-e2e
test-e2e:
	cd ${ISARDVDI_SRC}/frontend && yarn
	docker run -it \
	--rm --ipc=host \
	--network=host \
	-v "${ISARDVDI_SRC}/frontend:/frontend" \
	-w "/frontend" \
	mcr.microsoft.com/playwright:v1.38.0-jammy yarn playwright test

