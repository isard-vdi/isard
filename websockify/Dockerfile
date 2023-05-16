FROM golang:1.20-alpine as build

WORKDIR /go/src/gitlab.com/isard-vdi/isard/websockify

COPY go.mod /go/src/gitlab.com/isard-vdi/isard/websockify
COPY go.sum /go/src/gitlab.com/isard-vdi/isard/websockify

RUN go mod download

COPY . /go/src/gitlab.com/isard-vdi/isard/websockify

RUN go build -o websockify main.go


FROM alpine:3.17
MAINTAINER isard <info@isardvdi.com>

COPY --from=build /go/src/gitlab.com/isard-vdi/isard/websockify/websockify /

CMD [ "/websockify" ]
