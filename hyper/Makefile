all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/hyper-v$(VERSION) cmd/hyper/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-hyper:$(VERSION) ..

run:
	go run cmd/hyper/main.go
