#!/bin/sh
cat $RENEWED_LINEAGE/fullchain.pem $RENEWED_LINEAGE/privkey.pem > /certs/chain.pem

haproxy-reload
