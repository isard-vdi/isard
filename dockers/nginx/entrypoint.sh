#!/bin/bash

if [ ! -e "/etc/nginx/external/server-key.pem" ] || [ ! -e "/etc/nginx/external/server-cert.pem" ]
then
   echo ">> GENERATING NEW KEYS"
   bash /opt/auto-generate-certs.sh
fi

DH_PREGEN="/dh.pem"
if [ -f "$DH_PREGEN" ]
then
    mv /dh.pem /etc/nginx/external/
fi

if [ -z ${DH_SIZE+x} ]
then
  >&2 echo ">> no \$DH_SIZE specified using default" 
  DH_SIZE="2048"
fi


DH="/etc/nginx/external/dh.pem"

if [ ! -e "$DH" ]
then
  echo "#### Generating new dh.pem certificate file."
  echo "#### This can take a few minutes, please wait..."
  openssl dhparam -out "$DH" $DH_SIZE
fi

chmod 440 /etc/nginx/external/*

cat <<EOF
###############################################################
## IsardVDI docker system up.                                ##
##                                                           ##
## You can connect through your browser: https://<IP|domain> ##
##                                                           ##
## Logs are stored in your host /opt/isard/logs path         ##
###############################################################
EOF

#~ echo ">> exec docker CMD"
#~ echo "$@"
exec "$@"

