.PHONY: all
all: lint test build

.PHONY: build
build: rice
	# Incrustate the static files
	cd pkg/menus ; rice embed-go
	GO111MODULE=on CGO_ENABLED=0 go build -a -installsuffix cgo -ldflags "-s -w" -o isard-ipxe cmd/isard-ipxe/main.go

.PHONY: rice
rice:
	GO111MODULE=on go get github.com/GeertJohan/go.rice/rice

.PHONY: test
test:
	GO111MODULE=on go test -v -cover ./...

.PHONY: lint
lint: gometalinter
	gometalinter ./... --deadline=1h --exclude=_test

.PHONY: gometalinter
gometalinter:
	go get github.com/alecthomas/gometalinter
	gometalinter --install

