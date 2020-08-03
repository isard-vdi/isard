trap exit TERM
while :
do 
    sleep 12h
    certbot renew --http-01-port 8888
    cat /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/privkey.pem > /certs/chain.pem
    chmod 440 /certs/chain.pem
    mkdir -p /certs/letsencrypt/
    cp /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/* /certs/letsencrypt/
    kill -SIGUSR2 1
done
