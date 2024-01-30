#
# Build phase
#
ARG GOLANG_BUILD_IMAGE
ARG GOLANG_RUN_IMAGE

FROM ${GOLANG_BUILD_IMAGE} AS build

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

WORKDIR /

COPY . /build/guac

WORKDIR /build/guac

RUN CGO_ENABLED=0 go build -o bin/guac cmd/guac/guac.go


#
# Guac
#
FROM ${GOLANG_RUN_IMAGE}

COPY --from=build /build/guac/bin/guac /guac

CMD [ "/guac" ]
USER nobody
