#
# Build phase
#
FROM golang:1.20-alpine AS build

RUN apk add --no-cache \
    git

WORKDIR /build

COPY go.mod /build
COPY go.sum /build

RUN go mod download

COPY pkg /build/pkg
COPY check /build/check

WORKDIR /build/check

RUN CGO_ENABLED=0 go build -o bin/check cmd/check/main.go

#
# Testing
#
FROM jlesage/baseimage-gui:ubuntu-20.04

# Install dependencies
RUN add-pkg \
    wget \
    xterm \
    jq \
    curl \
    wireguard-tools \
    virt-viewer \
    remmina \
    remmina-plugin-rdp \
    inetutils-ping \
    firefox \
    dropbear \
    docker.io

# Install selenium & cia
RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.32.2/geckodriver-v0.32.2-linux64.tar.gz && \
    tar xzvf geckodriver-*-linux64.tar.gz && \
    chmod +x geckodriver && \
    mv geckodriver /usr/local/bin

COPY --from=build /build/check/bin/check /check

RUN echo "#!/bin/sh\nsleep infinity" > /startapp.sh && chmod +x /startapp.sh

# Set the name of the application.
ENV APP_NAME="IsardVDI Check"
ENV S6_LOGGING="1"
ENV USER_ID=0
ENV GROUP_ID=0

ENTRYPOINT [ "/init" ]
CMD [ "/check" ]
