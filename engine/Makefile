.PHONY: proto
proto:
	protoc -I "." -I pkg/proto/ pkg/proto/engine.proto --go_out=plugins=grpc:pkg/proto
	mv pkg/proto/github.com/isard-vdi/isard/engine/pkg/proto/* pkg/proto
	rm -r pkg/proto/github.com

test:
	go test -cover -race ./...