FROM marvambass/nginx-ssl-secure
MAINTAINER isard <info@isard.com>

COPY dockers/nginx/nginx.conf /etc/nginx/
RUN mkdir /viewers
ADD ./src/webapp/static/viewers /viewers
RUN mkdir /errors
ADD dockers/nginx/errors/* /errors/
COPY dockers/nginx/dh.pem /
COPY dockers/nginx/auto-generate-certs.sh /opt
COPY dockers/nginx/entrypoint.sh /opt/
RUN chmod 744 /opt/*
