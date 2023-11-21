#!/bin/sh
rm -rf /tmp/cfg
mkdir -p /tmp/cfg
for i in `find /usr/local/etc/haproxy/cfg -iname '*.cfg'`; do cp $i /tmp/cfg; done
echo "Contatenating cfg files for haproxy.cfg:"
ls -l /tmp/cfg
cat /tmp/cfg/* > /usr/local/etc/haproxy/haproxy.cfg

if [ -f /certs/custom-video-chain.pem ]
then
  sed -i 's/\/chain.pem/\/custom-video-chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
else
  sed -i 's/\/custom-video-chain.pem/\/chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
fi
LETSENCRYPT_DOMAIN="$VIDEO_DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" letsencrypt.sh

mkdir -p /usr/local/etc/haproxy/lists/external
touch /usr/local/etc/haproxy/lists/black.lst
touch /usr/local/etc/haproxy/lists/white.lst
touch /usr/local/etc/haproxy/lists/external/black.lst
