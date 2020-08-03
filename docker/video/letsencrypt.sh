if [ ! -f /certs/chain.pem ]; then
  if [ ! -z "$VIDEO_LETSENCRYPT_EMAIL" ]; then
       	/usr/bin/certbot certonly --standalone -d "$VIDEO_LETSENCRYPT_DNS" -m "$VIDEO_LETSENCRYPT_EMAIL" -n --agree-tos
        if [[ $? == 0 ]] ; then
                cat /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/fullchain.pem /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/privkey.pem > /certs/chain.pem
                chmod 440 /certs/chain.pem
                mkdir -p /certs/letsencrypt/
                cp /etc/letsencrypt/live/$VIDEO_LETSENCRYPT_DNS/* /certs/letsencrypt/
		/bin/sh -c '/letsencrypt-renew.sh' &
	fi
  fi
fi

