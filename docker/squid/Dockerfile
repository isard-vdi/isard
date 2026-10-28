FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS production

RUN apk -U upgrade --no-cache
RUN apk add --no-cache squid

# Blank the denied-request page in every language so a denial leaks no body.
RUN find /usr/share/squid/errors -name ERR_ACCESS_DENIED -exec sh -c ': > "$1"' _ {} \;

COPY docker/squid/run.sh /run.sh
COPY docker/squid/test_squid_conf.sh /test_squid_conf.sh
# Build-time gate: the generated config must pass the squid-config tests.
RUN sh /test_squid_conf.sh && rm /test_squid_conf.sh
#EXPOSE 8080

RUN chown -R squid:squid /etc/squid
USER squid

CMD ["/bin/sh", "/run.sh"]
