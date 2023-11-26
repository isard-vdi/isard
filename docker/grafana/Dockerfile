FROM grafana/grafana-oss:9.4.3 AS works

FROM grafana/grafana-oss:9.4.17

USER root

RUN rm -rf /usr/share/grafana/bin /usr/share/grafana/public

COPY --from=works /usr/share/grafana/bin /usr/share/grafana/bin
COPY --from=works /usr/share/grafana/public /usr/share/grafana/public

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    curl

USER grafana

COPY docker/grafana/grafana.ini /etc/grafana/grafana.ini
COPY docker/grafana/datasources /etc/grafana/provisioning/datasources
COPY docker/grafana/dashboards /etc/grafana/provisioning/dashboards

COPY docker/grafana/run.sh /run_isard.sh

ENTRYPOINT []
CMD /run_isard.sh && /run.sh
