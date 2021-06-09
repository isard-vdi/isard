#!/bin/sh
certbot renew --http-01-port 8080 --cert-name $LETSENCRYPT_DOMAIN
