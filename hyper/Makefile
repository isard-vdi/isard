all: gen test build docker

gen:
	protoc \
		--go_out=. \
		--go_opt=paths=source_relative \
		--go-grpc_out=. \
		--go-grpc_opt=paths=source_relative \
		--go-grpc-mock_out=. \
		--go-grpc-mock_opt=paths=source_relative \
	pkg/proto/hyper.proto

test:
	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	go build -o bin/hyper-v$(VERSION) cmd/hyper/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-hyper:$(VERSION) ..
