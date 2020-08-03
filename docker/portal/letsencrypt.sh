RENEW=0
if [[ ! -f /certs/chain.pem && ! -z "$WEBAPP_LETSENCRYPT_EMAIL" && ! -z "$WEBAPP_LETSENCRYPT_DNS" ]]; then
       	/usr/bin/certbot certonly --standalone -d "$WEBAPP_LETSENCRYPT_DNS" -m "$WEBAPP_LETSENCRYPT_EMAIL" -n --agree-tos
        if [[ $? == 0 ]] ; then
                cat /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/privkey.pem > /certs/chain.pem
                chmod 440 /certs/chain.pem
                mkdir -p /certs/letsencrypt/$WEBAPP_LETSENCRYPT_DNS
                cp /etc/letsencrypt/live/$WEBAPP_LETSENCRYPT_DNS/* /certs/letsencrypt/$WEBAPP_LETSENCRYPT_DNS/
		RENEW=1
	fi
fi

if [[ ! -f /certs/video.pem && ! -z "$VIDEO_LETSENCRYPT_EMAIL" && ! -z "$VIDEO_LETSENCRYPT_DNS"  ]]; then
       	/usr/bin/certbot certonly --standalone -d "$VIDEO_LETSENCRYPT_DNS" -m "$VIDEO_LETSENCRYPT_EMAIL" -n --agree-tos
        if [[ $? == 0 ]] ; then
                cat /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/privkey.pem > /certs/video.pem
                chmod 440 /certs/video.pem
                mkdir -p /certs/letsencrypt/$VIDEO_LETSENCRYPT_DNS
                cp /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/* /certs/letsencrypt/$VIDEO_LETSENCRYPT_DNS
		RENEW=1
	fi
fi

if [ $RENEW == 1 ]; then
	/bin/sh -c '/letsencrypt-check.sh' &
fi
