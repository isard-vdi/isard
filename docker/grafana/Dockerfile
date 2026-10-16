FROM grafana/grafana:13.1.8@sha256:1a8e58976a6cd349d1ffdd27a14b92053816c7c60e6b7e157013e9bf0b9cec5f

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
