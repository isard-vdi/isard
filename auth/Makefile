all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/auth-v$(VERSION) cmd/auth/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-auth:$(VERSION) ..

run:
	go run cmd/auth/main.go

