#!/bin/sh
# static job, not an envsubst template, so plain shell variables survive

root="${CONFIG_SOURCE_ROOT:-/opt/isard}"
# the dirs 72-config-borg.borg includes
dirs="assets authentication bastion certs config dnsmasq frontend monitor operations sshkeys wireguard"

for d in $dirs; do
    if [ -d "$root/$d" ] && [ -n "$(find "$root/$d" -type f -print 2>/dev/null | head -n1)" ]; then
        exit 0
    fi
done

echo "Fatal: config backup source is empty under $root; refusing to archive nothing"
exit 1
