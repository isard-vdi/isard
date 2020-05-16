VERSION=2.0.0

all: tidy test build docker

tidy:
	go mod tidy

test:
	go test -race -cover ./...

.PHONY: build
build:
	go build -o hyper-stats cmd/hyper-stats/main.go

docker:
	docker build -f build/package/Dockerfile -t isard/hyper-stats:${VERSION} .
