FROM alpine:3.11.3 

RUN apk add --no-cache squid
ADD dockers/squid/squid.conf /etc/squid/squid.conf
ADD dockers/squid/run.sh /run.sh
CMD ["/bin/sh", "/run.sh"]
