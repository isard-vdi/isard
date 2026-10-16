FROM grafana/grafana:13.1.2@sha256:d177053ab62253815f130d81504f77063baf5fd4ca93299d6048453bd31e047a

USER root

RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    curl \
    jq

# Baked in, outside the /var/lib/grafana volume, so nothing is downloaded at start.
ENV GF_PATHS_PLUGINS=/usr/share/grafana/plugins-isard
RUN mkdir -p /usr/share/grafana/plugins-isard && \
    grafana cli --pluginsDir /usr/share/grafana/plugins-isard plugins install grafana-pyroscope-app 3.0.0 && \
    grafana cli --pluginsDir /usr/share/grafana/plugins-isard plugins install grafana-lokiexplore-app 3.0.0 && \
    grafana cli --pluginsDir /usr/share/grafana/plugins-isard plugins install grafana-metricsdrilldown-app 3.0.0 && \
    chown -R grafana:root /usr/share/grafana/plugins-isard

USER grafana

COPY docker/grafana/grafana.ini /etc/grafana/grafana.ini
# owned by grafana so run.sh can lay custom files over the product ones
COPY --chown=grafana:root docker/grafana/datasources /etc/grafana/provisioning/datasources
COPY --chown=grafana:root docker/grafana/dashboards /etc/grafana/provisioning/dashboards
COPY --chown=grafana:root docker/grafana/alerting /etc/grafana/provisioning/alerting

COPY docker/grafana/run.sh /run_isard.sh

ENTRYPOINT []
CMD /run_isard.sh && /run.sh
