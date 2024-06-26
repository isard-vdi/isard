FROM registry.gitlab.com/isard/grafana:v11.1.0

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
