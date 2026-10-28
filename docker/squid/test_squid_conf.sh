#!/bin/sh
# Validates the squid.conf that run.sh generates, in the squid image. It covers
# the CONNECT fix (it needs host AND port), the comma-list handling, the
# information-disclosure hardening, and that squid parses the config with no
# error. Run it in the built image: `sh docker/squid/test_squid_conf.sh`.
set -e
dir=$(dirname "$0")
conf=/etc/squid/squid.conf
fail() { echo "FAIL: $1" >&2; exit 1; }

gen() { env VIDEO_HYPERVISOR_HOSTNAMES="$1" VIDEO_HYPERVISOR_PORTS="$2" sh "$dir/run.sh" --generate-only; }

# Defaults.
gen "" ""
grep -q '^acl SPICE_HOSTS dst isard-hypervisor$' "$conf" || fail "default hypervisor host"
grep -q '^acl SPICE_PORTS port 5900-7899$' "$conf"       || fail "default viewer port range"

# Comma-separated hostnames and port ranges both expand to space lists.
gen "h1,h2" "5900-6000,7000-7100"
grep -q '^acl SPICE_HOSTS dst h1 h2$' "$conf"                  || fail "comma hostnames"
grep -q '^acl SPICE_PORTS port 5900-6000 7000-7100$' "$conf"   || fail "comma port ranges"

# The access rule must require host AND port, and ports must be a port acl, not
# an address acl (the regression that let CONNECT reach any port).
grep -q '^http_access allow CONNECT SPICE_HOSTS SPICE_PORTS$' "$conf" || fail "CONNECT must require host AND port"
grep -q '^http_access deny all$' "$conf"                             || fail "must default-deny"
grep -q 'SPICE_PORTS dst' "$conf" && fail "ports must be a port acl, never dst"

# Information-disclosure hardening: version/hostname suppressed, squid headers
# stripped, and the denied-request page blanked so a denial leaks nothing.
for d in 'httpd_suppress_version_string on' 'via off' 'visible_hostname isard-squid' 'forwarded_for delete' \
         'reply_header_access Server deny all' 'reply_header_access X-Squid-Error deny all' 'reply_header_access Cache-Status deny all'; do
    grep -q "^$d\$" "$conf" || fail "missing hardening: $d"
done
for f in $(find /usr/share/squid/errors -name ERR_ACCESS_DENIED); do
    [ -s "$f" ] && fail "denied-request page not blanked: $f"
done

# The generated config must parse without an error (catches e.g. an invalid
# cache_dir, which squid would otherwise ignore silently). A `dst` acl with a
# hostname forces a DNS lookup at parse time, which the builder cannot do, so
# the parse check uses a literal IP; the directives being validated are the same.
gen "127.0.0.1" "5900-7899"
squid -k parse 2>/tmp/squid-parse.log || { cat /tmp/squid-parse.log >&2; fail "squid -k parse exited non-zero"; }
if grep -q 'ERROR:' /tmp/squid-parse.log; then
    grep 'ERROR:' /tmp/squid-parse.log >&2
    fail "squid -k parse reported an ERROR"
fi

echo "OK: squid config tests passed"
