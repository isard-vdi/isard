#!/bin/sh

if [[ -d "/custom/dashboards" ]]; then
    cp -RT /custom/dashboards/ /etc/grafana/provisioning/dashboards/
fi

if [[ -d "/custom/alerting" ]]; then
    cp -RT /custom/alerting/ /etc/grafana/provisioning/alerting/
fi

grafana-cli admin reset-admin-password $WEBAPP_ADMIN_PWD
