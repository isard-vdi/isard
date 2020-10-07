#!/bin/sh
set -e

#!/bin/sh

if [ ! -e "/certs/chain.pem" ]
then
   /bin/sh /letsencrypt.sh
fi
if [ ! -e "/certs/chain.pem" ]
then
   /bin/sh /auto-generate-certs.sh
fi



#if [ -z ${DH_SIZE+x} ]
#then
#  >&2 echo ">> no \$DH_SIZE specified using default"
#  DH_SIZE="2048"
#fi

#DH="/certs/dh.pem"

#if [ ! -e "$DH" ]
#then
#  echo "#### Generating new dh.pem certificate file."
#  echo "#### This can take a few minutes, please wait..."
#  openssl dhparam -out "$DH" $DH_SIZE
#fi

chmod 440 /certs/*



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
