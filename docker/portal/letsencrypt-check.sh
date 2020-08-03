#!/bin/sh
trap exit TERM
while :
do 
    sleep 12h
    certbot renew --http-01-port 8888
done
