#!/bin/sh
if [ -f /letsencrypt-hook-deploy-concatenante.sh ]
then
  mkdir -p /etc/letsencrypt/renewal-hooks/deploy/
  mv /letsencrypt-hook-deploy-concatenante.sh /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
fi

if [ -n "$LETSENCRYPT_EMAIL" ]
then
  LETSENCRYPT_DOMAIN="$DOMAIN" crond
  if [ ! -f /certs/chain.pem ]
  then
    if certbot certonly --standalone -d "$DOMAIN" -m "$LETSENCRYPT_EMAIL" -n --agree-tos
    then
      RENEWED_LINEAGE="/etc/letsencrypt/live/$DOMAIN" /etc/letsencrypt/renewal-hooks/deploy/concatenate.sh
    fi
  fi
fi
