#!/bin/sh
if [ -f /certs/custom-video-chain.pem ]
then
  sed -i 's/\/chain.pem/\/custom-video-chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
else
  sed -i 's/\/custom-video-chain.pem/\/chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
fi
LETSENCRYPT_DOMAIN="$VIDEO_DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" letsencrypt.sh
