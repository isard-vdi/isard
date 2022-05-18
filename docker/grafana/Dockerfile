FROM grafana/grafana-oss:8.5.2

COPY docker/grafana/grafana.ini /etc/grafana/grafana.ini
COPY docker/grafana/datasources /etc/grafana/provisioning/datasources
COPY docker/grafana/dashboards /etc/grafana/provisioning/dashboards

COPY docker/grafana/run.sh /run_isard.sh

ENTRYPOINT []
CMD /run_isard.sh && /run.sh
