proto:
	protoc -I "." -I pkg/proto/ pkg/proto/hyper.proto --go_out=plugins=grpc:pkg/proto
	mv pkg/proto/github.com/isard-vdi/isard/hyper/pkg/proto/* pkg/proto
	rm -r pkg/proto/github.com
