FROM grafana/grafana:12.4.5@sha256:26b8f35a9e4e4431995cf64c3f396505a4faf17bcfc19f9ed84943ec6bfd5ecd

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    curl \
    jq

USER grafana

COPY docker/grafana/grafana.ini /etc/grafana/grafana.ini
COPY docker/grafana/datasources /etc/grafana/provisioning/datasources
COPY docker/grafana/dashboards /etc/grafana/provisioning/dashboards

COPY docker/grafana/run.sh /run_isard.sh

ENTRYPOINT []
CMD /run_isard.sh && /run.sh
