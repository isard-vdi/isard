VERSION=2.0.0

all: tidy proto test build docker

tidy:
	go mod tidy

proto: tidy
	protoc -I "." -I pkg/proto/ pkg/proto/desktop-builder.proto --go_out=plugins=grpc:pkg/proto
	mv pkg/proto/github.com/isard-vdi/isard/desktop-builder/pkg/proto/* pkg/proto
	rm -r pkg/proto/github.com

test: proto
	go test -race -cover ./...

.PHONY: build
build:
	go build -o desktop-builder-bin cmd/desktop-builder/main.go

docker: test
	docker build -f build/package/Dockerfile -t isard/desktop-builder:${VERSION} ..
