FROM alpine:3.19 as production

RUN apk -U upgrade --no-cache
RUN apk add --no-cache squid

COPY docker/squid/run.sh /run.sh
#EXPOSE 8080

RUN chown -R squid:squid /etc/squid
USER squid

CMD ["/bin/sh", "/run.sh"]
