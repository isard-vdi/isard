FROM haproxy:alpine as production
RUN apk add openssl certbot
ADD docker/video/letsencrypt.sh /
ADD docker/video/letsencrypt-renew.sh /
ADD docker/video/auto-generate-certs.sh /
COPY docker/portal/docker-entrypoint.sh /usr/local/bin/
RUN rm /docker-entrypoint.sh
RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 docker-entrypoint.sh
ADD docker/video/haproxy.conf /usr/local/etc/haproxy/haproxy.cfg

