#
# IsardVDI - Isard iPXE
# https://github.com/isard-vdi/isard-ipxe
#

#
# Build stage
#

# Use golang 1.11 as build stage
FROM golang:1.11 as build

# Copy Isard iPXE
COPY . /go/src/github.com/isard-vdi/isard-ipxe

# Move to the correct directory
WORKDIR /go/src/github.com/isard-vdi/isard-ipxe

# Compile the binary
RUN make build

#
# Base stage
#

# Use alpine 3.8 as base
FROM alpine:3.8

# Copy the compiled binary from the build stage
COPY --from=build /go/src/github.com/isard-vdi/isard-ipxe/isard-ipxe /app/isard-ipxe

# Install the CA certificates
RUN apk add --update --no-cache ca-certificates

# Move to the correct directory
WORKDIR /data

# Expose the volume
VOLUME [ "/data" ]

# Expose the required port
EXPOSE 3000

# Run the service
CMD [ "/app/isard-ipxe" ]

