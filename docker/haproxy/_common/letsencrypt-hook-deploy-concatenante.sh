#!/bin/sh

# Enhanced certificate deployment script with better error handling and logging

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if RENEWED_LINEAGE is set and the certificate files exist
if [ -z "$RENEWED_LINEAGE" ]; then
    log "ERROR: RENEWED_LINEAGE environment variable not set"
    exit 1
fi

log "Deploying certificate from $RENEWED_LINEAGE"

if [ ! -d "$RENEWED_LINEAGE" ]; then
    log "ERROR: Certificate directory $RENEWED_LINEAGE does not exist"
    exit 1
fi

if [ ! -f "$RENEWED_LINEAGE/fullchain.pem" ] || [ ! -f "$RENEWED_LINEAGE/privkey.pem" ]; then
    log "ERROR: Certificate files not found in $RENEWED_LINEAGE"
    log "Directory contents:"
    ls -la "$RENEWED_LINEAGE" 2>/dev/null || log "Cannot list directory contents"
    exit 1
fi

# Verify certificate files are not empty
if [ ! -s "$RENEWED_LINEAGE/fullchain.pem" ]; then
    log "ERROR: fullchain.pem is empty"
    exit 1
fi

if [ ! -s "$RENEWED_LINEAGE/privkey.pem" ]; then
    log "ERROR: privkey.pem is empty"
    exit 1
fi

# Ensure /certs directory exists and is writable
if [ ! -d /certs ]; then
    log "Creating /certs directory"
    mkdir -p /certs
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to create /certs directory"
        exit 1
    fi
fi

if [ ! -w /certs ]; then
    log "ERROR: /certs directory is not writable"
    exit 1
fi

# Create a temporary file first to ensure atomic operation
TEMP_CHAIN="/certs/chain.pem.tmp.$$"
log "Creating temporary certificate file $TEMP_CHAIN"

# Concatenate certificate files for HAProxy
if cat "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" > "$TEMP_CHAIN"; then
    # Verify the temporary file was created and is not empty
    if [ -s "$TEMP_CHAIN" ]; then
        # Atomically move the temporary file to the final location
        if mv "$TEMP_CHAIN" /certs/chain.pem; then
            log "Certificate successfully deployed to /certs/chain.pem"

            # Set appropriate permissions
            chmod 640 /certs/chain.pem

            # Verify final file
            if [ -s /certs/chain.pem ]; then
                log "Final verification: /certs/chain.pem created successfully ($(stat -c%s /certs/chain.pem) bytes)"

                # Reload HAProxy
                log "Reloading HAProxy configuration"
                haproxy-reload

                log "Certificate deployment completed successfully"
                exit 0
            else
                log "ERROR: Final verification failed - /certs/chain.pem is empty"
                exit 1
            fi
        else
            log "ERROR: Failed to move temporary file to /certs/chain.pem"
            rm -f "$TEMP_CHAIN"
            exit 1
        fi
    else
        log "ERROR: Temporary certificate file is empty"
        rm -f "$TEMP_CHAIN"
        exit 1
    fi
else
    log "ERROR: Failed to concatenate certificate files"
    rm -f "$TEMP_CHAIN"
    exit 1
fi
