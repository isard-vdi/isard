#!/bin/sh
set -e

# Set debug path password
PASSWD=$(python3 -c 'import os,crypt,getpass; print(crypt.crypt(os.environ["WEBAPP_ADMIN_PWD"], crypt.mksalt(crypt.METHOD_SHA512)))')
sed -i "/^    user admin password/c\    user admin password $PASSWD" /usr/local/etc/haproxy/haproxy.cfg

/bin/sh /letsencrypt.sh

if [[ ! -e "/certs/chain.pem" ]]
then
   /bin/sh /auto-generate-certs.sh
fi

# first arg is `-f` or `--some-option`
if [ "${1#-}" != "$1" ]; then
        set -- haproxy "$@"
fi

if [ "$1" = 'haproxy' ]; then
        shift # "haproxy"
        # if the user wants "haproxy", let's add a couple useful flags
        #   -W  -- "master-worker mode" (similar to the old "haproxy-systemd-wrapper"; allows for reload via "SIGUSR2")
        #   -db -- disables background mode
        set -- haproxy -W -db "$@"
fi

exec "$@"
