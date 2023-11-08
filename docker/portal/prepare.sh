#!/bin/sh
rm -rf /tmp/cfg
mkdir -p /tmp/cfg
for i in `find /usr/local/etc/haproxy/cfg -iname '*.cfg'`; do cp $i /tmp/cfg; done
echo "Contatenating cfg files for haproxy.cfg:"
ls -l /tmp/cfg
cat /tmp/cfg/* > /usr/local/etc/haproxy/haproxy.cfg

# Set debug path password
PASSWD=$(python3 -c 'import os,crypt,getpass; print(crypt.crypt(os.environ["WEBAPP_ADMIN_PWD"], crypt.mksalt(crypt.METHOD_SHA512)))')
sed -i "/^    user admin password/c\    user admin password $PASSWD" /usr/local/etc/haproxy/haproxy.cfg

if [ -f /certs/custom-portal-chain.pem ]
then
  sed -i 's/\/chain.pem/\/custom-portal-chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
else
  sed -i 's/\/custom-portal-chain.pem/\/chain.pem/g' /usr/local/etc/haproxy/haproxy.cfg
fi

LETSENCRYPT_DOMAIN="$DOMAIN" LETSENCRYPT_EMAIL="$LETSENCRYPT_EMAIL" letsencrypt.sh

if [ ! -f /usr/local/etc/haproxy/lists/black.lst ]
then
  mkdir -p /usr/local/etc/haproxy/lists/external
  touch /usr/local/etc/haproxy/lists/black.lst
  touch /usr/local/etc/haproxy/lists/white.lst
  touch /usr/local/etc/haproxy/lists/external/ipsum.block
  touch /usr/local/etc/haproxy/lists/external/spamhaus.block
fi