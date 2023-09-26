ARG IMG
FROM ${IMG}

RUN apk update
RUN set -ex; \
    \
    apk add --no-cache \
        ffmpeg \
        procps \
        samba-client \
        supervisor \
#       libreoffice \
    ;

RUN set -ex; \
    \
    apk add --no-cache --virtual .build-deps \
        $PHPIZE_DEPS \
        imap-dev \
        krb5-dev \
        openssl-dev \
        samba-dev \
        bzip2-dev \
    ; \
    \
    docker-php-ext-configure imap --with-kerberos --with-imap-ssl; \
    docker-php-ext-install \
        bz2 \
        imap \
    ; \
    pecl install smbclient; \
    docker-php-ext-enable smbclient; \
    \
    runDeps="$( \
        scanelf --needed --nobanner --format '%n#p' --recursive /usr/local/lib/php/extensions \
            | tr ',' '\n' \
            | sort -u \
            | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
    )"; \
    apk add --virtual .nextcloud-phpext-rundeps $runDeps; \
    apk del .build-deps

COPY docker/nextcloud/requirements.txt .
RUN apk add --no-cache \
        py3-pip && \
    pip3 install --no-cache-dir -r requirements.txt && \
    rm requirements.txt

RUN mkdir -p \
    /var/log/supervisord \
    /var/run/supervisord \
;

COPY docker/nextcloud/init.sh /
RUN chmod +x /init.sh

COPY docker/nextcloud/src /src
COPY component/_common/src /src/_common

COPY docker/nextcloud/supervisord.conf /

ENV NEXTCLOUD_UPDATE=1

CMD ["/init.sh"]