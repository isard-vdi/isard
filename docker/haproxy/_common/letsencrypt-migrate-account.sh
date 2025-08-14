#!/bin/sh

# Utility script to migrate certificates from old Let's Encrypt accounts
# This script helps when certificates were created with deprecated API v1

echo "Let's Encrypt Account Migration Utility"
echo "======================================="

# Check required environment variables
if [ -z "$LETSENCRYPT_DOMAIN" ]; then
    echo "ERROR: LETSENCRYPT_DOMAIN environment variable not set"
    exit 1
fi

if [ -z "$LETSENCRYPT_EMAIL" ]; then
    echo "ERROR: LETSENCRYPT_EMAIL environment variable not set"
    exit 1
fi

CONF_FILE="/etc/letsencrypt/renewal/$LETSENCRYPT_DOMAIN.conf"
CERT_DIR="/etc/letsencrypt/live/$LETSENCRYPT_DOMAIN"

echo "Domain: $LETSENCRYPT_DOMAIN"
echo "Email: $LETSENCRYPT_EMAIL"
echo ""

# Check if certificate exists
if [ ! -d "$CERT_DIR" ]; then
    echo "No existing certificate found for $LETSENCRYPT_DOMAIN"
    echo "Use regular certificate issuance instead"
    exit 1
fi

# Show current certificate info
echo "Current certificate information:"
if command -v openssl > /dev/null 2>&1; then
    openssl x509 -in "$CERT_DIR/cert.pem" -noout -dates -subject 2>/dev/null || echo "Unable to read certificate details"
else
    echo "OpenSSL not available for certificate inspection"
fi
echo ""

# Check if renewal configuration exists
if [ -f "$CONF_FILE" ]; then
    echo "Current renewal configuration:"
    grep -E "^server|^account|^authenticator" "$CONF_FILE" 2>/dev/null || echo "No server/account info found"
    echo ""
    
    # Check if using old API
    if grep -q "acme-v01\.api\.letsencrypt\.org" "$CONF_FILE"; then
        echo "⚠️  WARNING: Configuration uses deprecated Let's Encrypt API v1"
        echo "   This will cause renewal failures"
        echo ""
    fi
else
    echo "No renewal configuration found"
    echo ""
fi

# Ask for confirmation
echo "This script will:"
echo "1. Backup the current renewal configuration"
echo "2. Re-issue the certificate with a new account using API v2"
echo "3. Deploy the new certificate"
echo ""
read -p "Do you want to proceed? (y/N): " confirm

case "$confirm" in
    [Yy]*)
        echo "Proceeding with certificate migration..."
        ;;
    *)
        echo "Migration cancelled"
        exit 0
        ;;
esac

# Backup existing configuration
if [ -f "$CONF_FILE" ]; then
    backup_file="${CONF_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "Backing up renewal configuration to $backup_file"
    cp "$CONF_FILE" "$backup_file"
fi

# Remove old configuration to force fresh registration
echo "Removing old renewal configuration"
rm -f "$CONF_FILE"

# Re-issue certificate
echo "Re-issuing certificate with new account..."
if certbot certonly --standalone -d "$LETSENCRYPT_DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos --http-01-port 8080 --force-renewal; then
    echo "✅ Certificate re-issued successfully!"
    
    # Deploy the certificate
    if [ -f /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh ]; then
        echo "Deploying certificate..."
        RENEWED_LINEAGE="$CERT_DIR" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
        echo "✅ Certificate deployed successfully!"
    else
        echo "⚠️  WARNING: Deployment hook not found"
        echo "   You may need to manually restart HAProxy"
    fi
    
    echo ""
    echo "Migration completed successfully!"
    echo "The certificate should now renew automatically"
else
    echo "❌ ERROR: Failed to re-issue certificate"
    
    # Restore backup if available
    if [ -f "${backup_file:-}" ]; then
        echo "Restoring backup configuration..."
        cp "$backup_file" "$CONF_FILE"
    fi
    
    exit 1
fi
