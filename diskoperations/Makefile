all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/diskoperations-v$(VERSION) cmd/diskoperations/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-diskoperations:$(VERSION) ..

run:
	go run cmd/diskoperations/main.go
