FROM alpine:3.11.3 as production

RUN apk add --no-cache bash tini

ENV GRAFANA_VERSION=8.0.6
RUN set -ex \
 && addgroup -S grafana \
 && adduser -S -G grafana grafana \
 && apk add --no-cache libc6-compat ca-certificates su-exec \
 && mkdir /tmp/setup \
 && wget -P /tmp/setup https://dl.grafana.com/oss/release/grafana-$GRAFANA_VERSION.linux-amd64.tar.gz \
 && tar -xzf /tmp/setup/grafana-$GRAFANA_VERSION.linux-amd64.tar.gz -C /tmp/setup --strip-components=1 \
 && install -m 755 /tmp/setup/bin/grafana-server /usr/local/bin/ \
 && install -m 755 /tmp/setup/bin/grafana-cli /usr/local/bin/ \
 && mkdir -p /grafana/datasources /grafana/dashboards /grafana/data /grafana/logs /grafana/plugins /var/lib/grafana \
 && cp -r /tmp/setup/public /grafana/public \
 && chown -R grafana:grafana /grafana \
 && ln -s /grafana/plugins /var/lib/grafana/plugins \
 && grafana-cli plugins update-all \
 && mkdir /grafana/conf \
 && cp /tmp/setup/conf/defaults.ini /grafana/conf/defaults.ini \
 && rm -rf /tmp/setup

COPY docker/grafana/run.sh /run.sh
COPY docker/grafana/grafana.db /grafana/data_init/grafana.db

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/bin/bash", "/run.sh"]
