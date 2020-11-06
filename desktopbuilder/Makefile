all: gen test build docker

gen:
	protoc \
		-I . \
		-I ../common/pkg/proto \
		--go_out=. \
		--go_opt=paths=source_relative \
		--go-grpc_out=. \
		--go-grpc_opt=paths=source_relative \
		--go-grpc-mock_out=. \
		--go-grpc-mock_opt=paths=source_relative \
	pkg/proto/desktopbuilder.proto

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/desktopbuilder-v$(VERSION) cmd/desktopbuilder/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-desktopbuilder:$(VERSION) ..
