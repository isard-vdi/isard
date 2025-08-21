#!/bin/sh

# Check if RENEWED_LINEAGE is set and the certificate files exist
if [ -z "$RENEWED_LINEAGE" ]; then
    echo "ERROR: RENEWED_LINEAGE environment variable not set"
    exit 1
fi

if [ ! -f "$RENEWED_LINEAGE/fullchain.pem" ] || [ ! -f "$RENEWED_LINEAGE/privkey.pem" ]; then
    echo "ERROR: Certificate files not found in $RENEWED_LINEAGE"
    exit 1
fi

# Concatenate certificate files for HAProxy
cat "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" > /certs/chain.pem

# Check if concatenation was successful
if [ $? -eq 0 ] && [ -s /certs/chain.pem ]; then
    echo "Certificate successfully deployed to /certs/chain.pem"
    haproxy-reload
else
    echo "ERROR: Failed to create /certs/chain.pem"
    exit 1
fi
