all: gen test

gen:
	# go generate ./...
	protoc \
		--go_out=. \
		--go_opt=paths=source_relative \
		--go-grpc_out=. \
		--go-grpc_opt=paths=source_relative \
		--go-grpc-mock_out=. \
		--go-grpc-mock_opt=paths=source_relative \
	proto/common/*.proto

	protoc \
		-I . \
		-I proto/common \
		--go_out=. \
		--go_opt=paths=source_relative \
		--go-grpc_out=. \
		--go-grpc_opt=paths=source_relative \
		--go-grpc-mock_out=. \
		--go-grpc-mock_opt=paths=source_relative \
	proto/{auth,controller,desktopbuilder,hyper,orchestrator}/*.proto

test:
	go test -cover -race ./...
