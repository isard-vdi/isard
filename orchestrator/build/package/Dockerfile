FROM golang:1.14-alpine as build

RUN apk add --no-cache \
	make \
    git

WORKDIR /go/src/github.com/isard-vdi/isard
COPY ./go.mod ./go.sum /go/src/github.com/isard-vdi/isard/
RUN go mod download

COPY . /go/src/github.com/isard-vdi/isard
WORKDIR /go/src/github.com/isard-vdi/isard/orchestrator

RUN make build

FROM alpine:3.11
MAINTAINER isard <info@isard.com>

COPY --from=build /go/src/github.com/isard-vdi/isard/orchestrator/orchestrator-bin /orchestrator

EXPOSE 8080

CMD [ "/orchestrator" ]
