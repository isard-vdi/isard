VERSION=2.0.0

all: tidy test build docker

tidy:
	go mod tidy

test: tidy
	go test -race -cover ./...

.PHONY: build
build:
	go build -o orchestrator-bin cmd/orchestrator/main.go

docker: test
	docker build -f build/package/Dockerfile -t isard/orchestrator:${VERSION} ..
