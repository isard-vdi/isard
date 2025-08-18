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
  if [ ! -f /certs/chain.pem ]
  then
    if certbot certonly --standalone -d "$LETSENCRYPT_DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos
    then
      # Execute the deployment hook manually for initial certificate
      if [ -f /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh ]
      then
        RENEWED_LINEAGE="/etc/letsencrypt/live/$(echo "$LETSENCRYPT_DOMAIN" | tr '[:upper:]' '[:lower:]')" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
      fi
    fi
  fi
fi
