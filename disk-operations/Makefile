VERSION=2.0.0

all: tidy proto test build docker

tidy:
	go mod tidy

proto:
	protoc -I "." -I pkg/proto/ pkg/proto/disk-operations.proto --go_out=plugins=grpc:pkg/proto
	mv pkg/proto/github.com/isard-vdi/isard/disk-operations/pkg/proto/* pkg/proto
	rm -r pkg/proto/github.com

test:
	go test -race -cover ./...

.PHONY: build
build:
	go build -o disk-operations cmd/disk-operations/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/disk-operations:${VERSION} .