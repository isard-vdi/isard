all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/orchestrator-v$(VERSION) cmd/orchestrator/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-orchestrator:$(VERSION) ..

run:
	go run cmd/orchestrator/main.go
