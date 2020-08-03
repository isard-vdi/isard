#!/bin/sh
echo "Domain(s) $domain renewed. Restarting haproxy..."
    cat /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/privkey.pem > /certs/chain.pem
    chmod 440 /certs/chain.pem
    mkdir -p /certs/letsencrypt/$WEBAPP_LETSENCRYPT_DNS
    cp /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/* /certs/letsencrypt/$WEBAPP_LETSENCRYPT_DNS/

    cat /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/privkey.pem > /certs/video.pem
    chmod 440 /certs/video.pem
    mkdir -p /certs/letsencrypt/$VIDEO_LETSENCRYPT_DNS
    cp /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/* /certs/letsencrypt/$VIDEO_LETSENCRYPT_DNS/

kill -SIGUSR2 1
