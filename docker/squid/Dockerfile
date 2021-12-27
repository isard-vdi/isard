FROM alpine:3.15.0 as production

RUN apk add --no-cache squid
COPY docker/squid/run.sh /run.sh
#EXPOSE 8080
CMD ["/bin/sh", "/run.sh"]

