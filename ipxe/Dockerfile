#
# IsardVDI - Isard iPXE
# https://github.com/isard-vdi/isard-ipxe
#

#
# Build stage
#

# Use golang 1.11 as stage stage
FROM golang:1.11 as build

# Download Isard iPXE
WORKDIR /go/src/github.com/isard-vdi
RUN git clone https://github.com/isard-vdi/isard-ipxe

# Move to the correct directory
WORKDIR /go/src/github.com/isard-vdi/isard-ipxe

# Compile the binary
RUN CGO_ENABLED=0 go build -a -ldflags "-s -w" -o isard-ipxe cmd/isard-ipxe/main.go

# Create the user
RUN adduser --disabled-password --gecos '' app

#
# Base stage
#

# Use alpine 3.8 as base
FROM alpine:3.8

# Copy the /etc/passwd (which contains the user 'app') from the build stage
COPY --from=build /etc/passwd /etc/passwd

# Copy the compiled binary from the build stage
COPY --from=build /go/src/github.com/isard-vdi/isard-ipxe/isard-ipxe /app/isard-ipxe

# Move to the correct directory
WORKDIR /data

# Change the directory permissions
RUN chown app /data

# Use the 'app' user
USER app

# Expose the volume
VOLUME [ "/data" ]

# Expose the required port
EXPOSE 3000

# Run the service
CMD [ "/app/isard-ipxe" ]

