FROM haproxy:alpine as production
RUN apk add openssl certbot
ADD docker/portal/letsencrypt.sh /
ADD docker/portal/letsencrypt-check.sh /
ADD docker/portal/deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/
ADD docker/portal/auto-generate-certs.sh /
COPY docker/portal/docker-entrypoint.sh /usr/local/bin/
RUN rm /docker-entrypoint.sh
RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 docker-entrypoint.sh
ADD docker/portal/haproxy.conf /usr/local/etc/haproxy/haproxy.cfg
