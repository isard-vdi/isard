#!/bin/sh

CONF_FILE="/etc/letsencrypt/renewal/$LETSENCRYPT_DOMAIN.conf"

if [ -f "$CONF_FILE" ]; then
    # If current certificate was generated with a different authenticator,
    # we need to change it to standalone for the renewal or it won't work.
    sed -i '/^pref_challs/d' "$CONF_FILE"
    sed -i 's/^authenticator.*/authenticator = standalone/' "$CONF_FILE"
fi

certbot renew --http-01-port 8080 --cert-name $LETSENCRYPT_DOMAIN
