all: gen test build docker

gen:
	go generate ./...

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/backend-v$(VERSION) cmd/backend/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-backend:$(VERSION)