#!/bin/bash

if [ ! -f /grafana/data/grafana.db ]; then
  echo "Creating default config for grafana"
  cp -R /grafana/data_init/* /grafana/data/
  chown -R grafana:grafana /grafana
fi

sed -i "/^domain/c\domain = localhost" /grafana/conf/defaults.ini
sed -i "/^root_url/c\root_url = %(protocol)s://%(domain)s:%(http_port)s/monitor" /grafana/conf/defaults.ini
sed -i "/^serve_from_sub_path/c\serve_from_sub_path = true" /grafana/conf/defaults.ini

sed -i "/enable anonymous access/{N;s/enabled.*/enabled = true/}" /grafana/conf/defaults.ini
sed -i "/^org_name/c\org_name = IsardVDI" /grafana/conf/defaults.ini

cd /grafana

grafana-cli admin reset-admin-password $WEBAPP_ADMIN_PWD

/usr/local/bin/grafana-server --homepath=/grafana >> /grafana/logs/grafana.log

