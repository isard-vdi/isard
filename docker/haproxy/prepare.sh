#!/bin/sh

if [ ! -f /usr/local/etc/haproxy/bastion_domains/subdomains.map ]
then
  echo "Creating /usr/local/etc/haproxy/bastion_domains/subdomains.map"
  mkdir -p /usr/local/etc/haproxy/bastion_domains
  touch /usr/local/etc/haproxy/bastion_domains/subdomains.map
fi

if [ ! -f /usr/local/etc/haproxy/bastion_domains/individual.map ]
then
  echo "Creating /usr/local/etc/haproxy/bastion_domains/individual.map"
  touch /usr/local/etc/haproxy/bastion_domains/individual.map
fi

tmp_dir=$( mktemp -d )
for i in `find /usr/local/etc/haproxy/cfg/_base -iname '*.cfg'`; do cp $i "$tmp_dir"; done
for i in `find /usr/local/etc/haproxy/cfg/$CFG -iname '*.cfg'`; do cp $i "$tmp_dir"; done
for i in `find /usr/local/etc/haproxy/cfg/customs -iname '*.cfg'`; do cp $i "$tmp_dir"; done
echo "Building haproxy.cfg for flavour: $CFG"
if [ "$CFG" != "portal" ] && [ "$CFG" != "video" ]
then
  rm "$tmp_dir"/04_00_fe_nonsecured_begin.cfg
fi
if [ "$DEVELOPMENT" = "true" ]
then
  echo "Development mode: excluding abuse protection configuration"
  rm -f "$tmp_dir"/16_04_fe_secured_abuse.cfg
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
