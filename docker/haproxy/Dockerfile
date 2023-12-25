ARG HAPROXY_RUN_IMAGE
FROM ${HAPROXY_RUN_IMAGE} as production

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache openssl certbot

COPY docker/haproxy/prepare.sh /usr/local/sbin/
COPY docker/haproxy/_common/letsencrypt-hook-deploy-concatenante.sh /
COPY docker/haproxy/_common/letsencrypt.sh /usr/local/sbin/
COPY docker/haproxy/_common/letsencrypt-renew-cron.sh /etc/periodic/daily/letsencrypt-renew
COPY docker/haproxy/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/haproxy/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/haproxy/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 /docker-entrypoint.sh

COPY docker/haproxy/cfg /usr/local/etc/haproxy/cfg