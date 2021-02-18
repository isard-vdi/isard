all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/controller-v$(VERSION) cmd/controller/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-controller:$(VERSION) ..

run:
	go run cmd/controller/main.go
