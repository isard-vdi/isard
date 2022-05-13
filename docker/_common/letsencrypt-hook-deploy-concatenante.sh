#!/bin/sh
cat $RENEWED_LINEAGE/fullchain.pem $RENEWED_LINEAGE/privkey.pem > /certs/chain.pem
cp $RENEWED_LINEAGE/fullchain.pem /certs/server-cert.pem
cp $RENEWED_LINEAGE/privkey.pem /certs/server-key.pem

haproxy-reload
