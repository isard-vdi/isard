FROM marvambass/nginx-ssl-secure as production
MAINTAINER isard <info@isard.com>

COPY dockers/nginx/nginx.conf /etc/nginx/
RUN mkdir /viewers
ADD ./src/webapp/static/viewers /viewers
RUN mkdir /errors
ADD dockers/nginx/errors/* /errors/
ADD dockers/nginx/maintenance/* /maintenance/
ADD dockers/nginx/maintenance.* /
RUN touch /etc/nginx/maintenance.conf
COPY dockers/nginx/dh.pem /
COPY dockers/nginx/auto-generate-certs.sh /opt
COPY dockers/nginx/entrypoint.sh /opt/
RUN chmod 744 /opt/*

FROM production as development
