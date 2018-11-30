#
# IsardVDI - Isard iPXE
# https://github.com/isard-vdi/isard-ipxe
#

#
# Build stage
#

# Use golang 1.11 as build stage
FROM golang:1.11 as build

# Move to the correct directory
COPY . /go/src/github.com/isard-vdi/isard-ipxe/
WORKDIR /go/src/github.com/isard-vdi/isard-ipxe

# Compile the binary
RUN make build

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

# Create the data directory and set the correct permissions
RUN mkdir /data
RUN chown app /data

# Move to the correct directory
WORKDIR /data

# Use the 'app' user
USER app

# Expose the volume
VOLUME [ "/data" ]

# Expose the required port
EXPOSE 3000

# Run the service
CMD [ "/app/isard-ipxe" ]

