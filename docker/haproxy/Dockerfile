ARG HAPROXY_RUN_IMAGE

# Hack to be able to use an arg as a COPY --from
# https://stackoverflow.com/a/63472135
ARG DOCKER_IMAGE_PREFIX=registry.gitlab.com/isard/isardvdi/
ARG DOCKER_IMAGE_TAG
FROM ${DOCKER_IMAGE_PREFIX}haproxy-bastion-sync:$DOCKER_IMAGE_TAG as haproxy-bastion-sync

FROM ${HAPROXY_RUN_IMAGE} as production

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache openssl acme.sh

# Copy haproxy-bastion-sync binary
COPY --from=haproxy-bastion-sync /haproxy-bastion-sync /usr/local/bin/haproxy-bastion-sync

# Copy HAProxy scripts and configs
COPY docker/haproxy/_common/prepare.sh /usr/local/sbin/
COPY docker/haproxy/_common/auto-generate-certs.sh /usr/local/sbin/
COPY docker/haproxy/_common/haproxy-reload /usr/local/bin/haproxy-reload
COPY docker/haproxy/_common/haproxy-docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY docker/haproxy/_common/acme-management.sh /usr/local/bin/acme-management.sh

RUN ln -s /usr/local/bin/docker-entrypoint.sh /
RUN chmod 775 \
    /docker-entrypoint.sh \
    /usr/local/sbin/prepare.sh \
    /usr/local/sbin/auto-generate-certs.sh \
    /usr/local/bin/haproxy-reload \
    /usr/local/bin/acme-management.sh \
    /usr/local/bin/haproxy-bastion-sync

COPY docker/haproxy/cfg /usr/local/etc/haproxy/cfg
WORKDIR /usr/local/etc/haproxy
