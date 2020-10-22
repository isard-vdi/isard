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
	pkg/proto/controller.proto

test:
	go test -cover -race ./...

build:
	mkdir -p bin
	go build -o bin/controller-v$(VERSION) cmd/controller/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/isardvdi-controller:$(VERSION) ..
