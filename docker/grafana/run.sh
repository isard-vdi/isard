#!/bin/sh

if [[ -d "/custom/dashboards" ]]; then
    cp -RT /custom/dashboards/ /etc/grafana/provisioning/dashboards/
fi

if [[ -d "/custom/alerting" ]]; then
    cp -RT /custom/alerting/ /etc/grafana/provisioning/alerting/
fi

# The storage-governor alerting provisions a Telegram contact point. Grafana
# treats an empty bot token as a FATAL provisioning error ("could not find Bot
# Token in settings") and crash-loops on startup — it does not degrade to a
# warning. Telegram delivery is opt-in, so drop that file when its secrets are
# unset and let grafana start; the same alerts are carried by the Prometheus
# rules (docker/prometheus/rules/storage_governor.rules.yml) with no secret.
# This runs OUTSIDE the /custom block on purpose: the file is also baked into
# /etc/grafana/provisioning/alerting by the image (see docker/grafana/Dockerfile),
# so an install with no /custom overlay must still have it removed.
if [ -z "$GRAFANA_TELEGRAM_TOKEN" ] || [ -z "$GRAFANA_TELEGRAM_CHAT_ID" ]; then
    rm -f /etc/grafana/provisioning/alerting/storage_governor.yaml
fi

cat << EOF > /etc/grafana/provisioning/jwks.json
{
    "keys": [
    	{"kty":"oct","alg":"HS256","k":"$(echo -n "$API_ISARDVDI_SECRET" | base64 -w 0 | tr -d '=')"}
    ]
}
EOF

grafana-cli admin reset-admin-password $WEBAPP_ADMIN_PWD

if [[ -x "/custom/entrypoint.sh" ]]; then
    /custom/entrypoint.sh
fi
