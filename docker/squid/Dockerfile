FROM alpine:3.22@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce as production

RUN apk -U upgrade --no-cache
RUN apk add --no-cache squid

COPY docker/squid/run.sh /run.sh
#EXPOSE 8080

RUN chown -R squid:squid /etc/squid
USER squid

CMD ["/bin/sh", "/run.sh"]
