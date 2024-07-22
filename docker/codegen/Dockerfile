FROM alpine:3.20

RUN apk -U upgrade --no-cache
RUN apk add --no-cache go python3 npm protoc

RUN go install github.com/bufbuild/buf/cmd/buf@v1.34.0 && \
    go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.4.0 && \
    go install github.com/pseudomuto/protoc-gen-doc/cmd/protoc-gen-doc@v1.5.1 && \
    go install github.com/ogen-go/ogen/cmd/ogen@v1.2.2 && \
    go install github.com/vektra/mockery/v2@v2.40.3 && \
    cp ~/go/bin/* /usr/bin/
RUN python3 -m venv /venv && \
    source /venv/bin/activate && \
    pip3 install \
    	"betterproto[compiler]==2.0.0-beta6" \
	"grpcio-tools==1.64.1"
RUN npm install --global @bufbuild/protoc-gen-es@1.10.0

COPY docker/codegen/gen.sh /gen.sh

WORKDIR /build

CMD [ "/gen.sh" ]
