VERSION=2.0.0-rc1

all: tidy test build docker

tidy:
	go mod tidy

test:
	go test -race -cover ./...

.PHONY: build
build:
	go build -o backend cmd/backend/*.go

docker:
	docker build -t isard/backend:${VERSION} -f build/package/Dockerfile --no-cache .
	docker push isard/backend:${VERSION}

