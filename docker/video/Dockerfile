FROM haproxy:2.3.9-alpine as production
RUN apk add openssl certbot
COPY docker/video/prepare.sh /usr/local/sbin/
COPY docker/_common/letsencrypt-hook-deploy-concatenante.sh /
COPY docker/_common/letsencrypt.sh /usr/local/sbin/
COPY docker/_common/letsencrypt-renew-cron.sh /etc/periodic/daily/letsencrypt-renew
COPY docker/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN rm /docker-entrypoint.sh
RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 docker-entrypoint.sh
ADD docker/video/haproxy.conf /usr/local/etc/haproxy/haproxy.cfg
