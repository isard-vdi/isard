#!/bin/sh

tmp_dir=$( mktemp -d )

for i in `find /usr/local/etc/haproxy/cfg/customs -iname '*.cfg'`; do cp $i "$tmp_dir"; done
for i in `find /usr/local/etc/haproxy/cfg/_base -iname '*.cfg'`; do cp $i "$tmp_dir"; done

for part in $FLAVOUR; do
  if [ "$part" = "hypervisor" ] || [ "$part" = "video-standalone" ]
  then
          part="video"
  fi

  for i in `find /usr/local/etc/haproxy/cfg/$part -iname '*.cfg'`; do cp $i "$tmp_dir"; done
done

echo "Building haproxy.cfg for flavour: $FLAVOUR"
if [ "$DEVELOPMENT" = "true" ]
then
  echo "Development mode: excluding abuse protection configuration"
  rm -f "$tmp_dir"/16_04_fe_http_secured_abuse.cfg
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

if [ -n "$ACME_EMAIL" ]; then
    if ! acme-management.sh register; then
        echo "WARNING: ACME account registration failed for $ACME_EMAIL"
    fi
fi

mkdir -p /usr/local/etc/haproxy/lists/external
touch /usr/local/etc/haproxy/lists/black.lst
touch /usr/local/etc/haproxy/lists/white.lst
touch /usr/local/etc/haproxy/lists/external/black.lst
