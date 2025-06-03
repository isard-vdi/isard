#!/bin/sh

tmp_dir=$( mktemp -d )
for i in `find /usr/local/etc/haproxy/cfg/_base -iname '*.cfg'`; do cp $i "$tmp_dir"; done
for i in `find /usr/local/etc/haproxy/cfg/$CFG -iname '*.cfg'`; do cp $i "$tmp_dir"; done
for i in `find /usr/local/etc/haproxy/cfg/customs -iname '*.cfg'`; do cp $i "$tmp_dir"; done
echo "Building haproxy.cfg for flavour: $CFG"
if [ "$CFG" != "portal" ] && [ "$CFG" != "video" ]
then
  rm "$tmp_dir"/04_00_fe_nonsecured_begin.cfg
fi
cat "$tmp_dir"/*.cfg > /usr/local/etc/haproxy/haproxy.cfg

PASSWD=$(mkpasswd -m sha-512 $WEBAPP_ADMIN_PWD)
sed -i "/^    user admin password/c\    user admin password $PASSWD" /usr/local/etc/haproxy/haproxy.cfg

if [ -f /certs/custom-portal-chain.pem ]
then
  sed -i 's/\/chain.pem/\/custom-portal-chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
else
  sed -i 's/\/custom-portal-chain.pem/\/chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
fi

if [ -n "$VIDEO_DOMAIN" ]
then
  LETSENCRYPT_DOMAIN="$VIDEO_DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" letsencrypt.sh
else
  LETSENCRYPT_DOMAIN="$DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" letsencrypt.sh
fi

mkdir -p /usr/local/etc/haproxy/lists/external
touch /usr/local/etc/haproxy/lists/black.lst
touch /usr/local/etc/haproxy/lists/white.lst
touch /usr/local/etc/haproxy/lists/external/black.lst
