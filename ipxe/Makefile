.PHONY: build
build: test
	GO111MODULE=on CGO_ENABLED=0 go build -a -installsuffix cgo -ldflags "-s -w" -o isard-ipxe cmd/isard-ipxe/main.go

.PHONY: test
test: lint
	GO111MODULE=on go test -v -cover ./...

.PHONY: lint
lint:
	GO111MODULE=on gometalinter ./... --deadline=1h --exclude=_test
