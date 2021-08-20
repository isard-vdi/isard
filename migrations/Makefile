# all: test build docker

# test:
# 	go test -cover -race ./...

.PHONY: build
build:
	mkdir -p bin
	CGO_ENABLED=0 GOOS=linux go build -a -ldflags '-extldflags "-static"' -o bin/migrations-v$(VERSION) cmd/migrations/main.go

# docker:
# 	docker build -f build/package/Dockerfile -t $(DOCKER_IMAGE)migrations:$(VERSION) ..

# run:
# 	go run cmd/migrations/main.go
