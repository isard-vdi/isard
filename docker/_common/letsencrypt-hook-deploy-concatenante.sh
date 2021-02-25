#!/bin/sh
cat $RENEWED_LINEAGE/fullchain.pem $RENEWED_LINEAGE/privkey.pem > /certs/chain.pem

kill -SIGUSR2 1
