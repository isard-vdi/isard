FROM alpine:3.18 as production

RUN apk -U upgrade --no-cache
RUN apk add --no-cache squid

COPY docker/squid/run.sh /run.sh
#EXPOSE 8080
CMD ["/bin/sh", "/run.sh"]

