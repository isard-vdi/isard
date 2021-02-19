all: gen test build docker

gen:

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/desktopbuilder-v$(VERSION) cmd/desktopbuilder/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-desktopbuilder:$(VERSION) ..

run:
	go run cmd/desktopbuilder/main.go
