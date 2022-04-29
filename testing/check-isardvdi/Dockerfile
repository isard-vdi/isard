#
# Build phase
#
FROM golang:1.18-alpine AS build

RUN apk add --no-cache \
    git

WORKDIR /build

RUN git clone https://gitlab.com/isard/isardvdi-cli

WORKDIR /build/isardvdi-cli

RUN go mod download

RUN CGO_ENABLED=0 go build -o isardvdi-cli main.go

#
# Testing
#
FROM jlesage/baseimage-gui:ubuntu-20.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    xterm \
    jq \
    curl \
    wireguard-tools \
    virt-viewer \
    remmina \
    inetutils-ping \
    cowsay

COPY testing/check-isardvdi/isard.cow /isard.cow
COPY --from=build /build/isardvdi-cli/isardvdi-cli /usr/local/bin

RUN echo "#!/bin/sh\nsleep infinity" > /startapp.sh && chmod +x /startapp.sh
COPY testing/check-isardvdi/check_isardvdi_works.sh /check_isardvdi_works.sh

# Set the name of the application.
ENV APP_NAME="IsardVDI Testing"
ENV S6_LOGGING="1"
ENV USER_ID=0
ENV GROUP_ID=0


ENTRYPOINT [ "/init" ]
CMD [ "/check_isardvdi_works.sh" ]
