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
    if certbot certonly --standalone -d "$LETSENCRYPT_DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos --http-01-port 8080
    then
      # Execute the deployment hook manually for initial certificate
      if [ -f /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh ]
      then
        RENEWED_LINEAGE="/etc/letsencrypt/live/$(echo "$LETSENCRYPT_DOMAIN" | tr '[:upper:]' '[:lower:]')" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
      fi
    fi
  fi
fi
