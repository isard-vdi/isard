#!/bin/sh

if [[ -d "/custom/dashboards" ]]; then
    cp -RT /custom/dashboards/ /etc/grafana/provisioning/dashboards/
fi

if [[ -d "/custom/alerting" ]]; then
    cp -RT /custom/alerting/ /etc/grafana/provisioning/alerting/
fi

cat << EOF > /etc/grafana/provisioning/jwks.json
{
    "keys": [
    	{"kty":"oct","alg":"HS256","k":"$(echo -n "$API_ISARDVDI_SECRET" | base64 -w 0 | tr -d '=')"}
    ]
}
EOF

if [[ -x "/custom/entrypoint.sh" ]]; then
    /custom/entrypoint.sh
fi
