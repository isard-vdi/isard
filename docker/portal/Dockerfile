FROM haproxy:alpine as production
RUN apk add openssl certbot
ADD docker/portal/letsencrypt.sh /
ADD docker/portal/letsencrypt-check.sh /
ADD docker/portal/deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/
ADD docker/portal/auto-generate-certs.sh /
ADD docker/portal/docker-entrypoint.sh /
RUN chmod 775 docker-entrypoint.sh
ADD docker/portal/haproxy.conf /usr/local/etc/haproxy/haproxy.cfg
