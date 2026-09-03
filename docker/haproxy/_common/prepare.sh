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

# One acl line per extra name: haproxy expands "${VAR}" to a single pattern, so
# a list cannot travel in one variable. Sorts inside the secured frontend.
if [ -n "$ACME_EXTRA_DOMAINS" ]; then
  printf '%s\n' "$ACME_EXTRA_DOMAINS" | tr ',' '\n' | while read -r extra_domain; do
    [ -n "$extra_domain" ] || continue
    printf '  acl is_domain var(sess.ssl_sni) -m str -i "%s"\n' "$extra_domain"
  done > "$tmp_dir/05_01_fe_tcp_secured_extra_domains.cfg"
fi

echo "Building haproxy.cfg for flavour: $FLAVOUR"
if [ "$USAGE" = "devel" ]
then
  echo "Development mode: excluding abuse protection configuration"
  rm -f "$tmp_dir"/16_04_fe_http_secured_abuse.cfg
fi
cat "$tmp_dir"/*.cfg > /usr/local/etc/haproxy/haproxy.cfg

# Generate crt-list for dynamic SSL certificate management.
if [ -f /certs/custom-portal-chain.pem ]; then
  echo "/certs/custom-portal-chain.pem" > /certs/crt-list.cfg
else
  echo "/certs/chain.pem" > /certs/crt-list.cfg
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
