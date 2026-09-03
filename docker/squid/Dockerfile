FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b as production

RUN apk -U upgrade --no-cache
RUN apk add --no-cache squid

COPY docker/squid/run.sh /run.sh
#EXPOSE 8080

RUN chown -R squid:squid /etc/squid
USER squid

CMD ["/bin/sh", "/run.sh"]
