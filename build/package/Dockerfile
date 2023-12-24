#
# Build phase
#
FROM golang:1.21-alpine as build

RUN apk add --no-cache \
    git

COPY . /build
WORKDIR /build


RUN go build -o guac cmd/guac/guac.go

#
# Guac
#
FROM alpine:3.19

COPY --from=build /build/guac /guac

EXPOSE 4567

CMD [ "/guac" ]
USER nobody
