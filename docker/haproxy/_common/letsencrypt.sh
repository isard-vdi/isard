#!/bin/sh
if [ -f /letsencrypt-hook-deploy-concatenante.sh ]
then
  mkdir -p /etc/letsencrypt/renewal-hooks/deploy/
  mv /letsencrypt-hook-deploy-concatenante.sh /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
  chmod +x /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
fi

if [ -n "$LETSENCRYPT_DOMAIN" -a -n "$LETSENCRYPT_EMAIL" ]
then
  LETSENCRYPT_DOMAIN="$LETSENCRYPT_DOMAIN" crond

  # Check for existing certificate with old API configuration
  CONF_FILE="/etc/letsencrypt/renewal/$LETSENCRYPT_DOMAIN.conf"
  if [ -f "$CONF_FILE" ] && grep -q "acme-v01\.api\.letsencrypt\.org" "$CONF_FILE"; then
    echo "Detected certificate with deprecated API v1, migrating to API v2"
    # Update server URL to current Let's Encrypt API v2
    sed -i 's|acme-v01\.api\.letsencrypt\.org/directory|acme-v02.api.letsencrypt.org/directory|g' "$CONF_FILE"
  fi

  if [ ! -f /certs/chain.pem ]
  then
    # During startup, HAProxy is not running yet, so we can use port 80 directly
    echo "Attempting to get Let's Encrypt certificate using port 80 (startup phase)"
    if certbot certonly --standalone -d "$LETSENCRYPT_DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos --http-01-port 80
    then
      echo "Let's Encrypt certificate obtained successfully"

      # Wait for filesystem sync and verify certificate files exist
      sleep 2
      CERT_PATH="/etc/letsencrypt/live/$(echo "$LETSENCRYPT_DOMAIN" | tr '[:upper:]' '[:lower:]')"

      # Verify certificate files exist before deployment
      if [ ! -d "$CERT_PATH" ]; then
        echo "ERROR: Certificate directory $CERT_PATH does not exist"
        echo "Available directories in /etc/letsencrypt/live/:"
        ls -la /etc/letsencrypt/live/ 2>/dev/null || echo "No directories found"
        return 1
      fi

      if [ ! -f "$CERT_PATH/fullchain.pem" ] || [ ! -f "$CERT_PATH/privkey.pem" ]; then
        echo "ERROR: Certificate files missing in $CERT_PATH"
        echo "Contents of $CERT_PATH:"
        ls -la "$CERT_PATH" 2>/dev/null || echo "Directory not accessible"
        return 1
      fi

      # Execute the deployment hook manually for initial certificate
      if [ -f /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh ]
      then
        echo "Deploying certificate to HAProxy format..."
        if RENEWED_LINEAGE="$CERT_PATH" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
        then
          echo "Certificate deployment successful"
          # Verify the final chain.pem was created
          if [ -f /certs/chain.pem ] && [ -s /certs/chain.pem ]; then
            echo "Successfully created /certs/chain.pem"
          else
            echo "ERROR: /certs/chain.pem was not created or is empty"
            return 1
          fi
        else
          echo "ERROR: Certificate deployment hook failed"
          return 1
        fi
      else
        echo "ERROR: Deployment hook not found at /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh"
        return 1
      fi
    else
      echo "Let's Encrypt certificate generation failed, will fallback to self-signed certificates"
      return 1
    fi
  fi
fi
