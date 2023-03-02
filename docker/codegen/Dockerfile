FROM alpine:3.17

RUN apk add --no-cache go python3 npm
RUN go install github.com/bufbuild/buf/cmd/buf@v1.15.0 && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.28.1 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0 && \
    go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@v1.5.1 && \
    cp ~/go/bin/* /usr/bin/
RUN python3 -m venv /venv && \
    source /venv/bin/activate && \
    pip3 install "betterproto[compiler]==2.0.0-beta5"
RUN npm install --global @bufbuild/protoc-gen-es@1.0.0

WORKDIR /build

CMD [ "ash", "-c", "source /venv/bin/activate && HOME=/tmp buf generate" ]
