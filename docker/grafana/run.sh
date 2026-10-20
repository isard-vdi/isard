#!/bin/sh

PROV=/etc/grafana/provisioning
mkdir -p "$PROV/custom_dashboards"

# A custom file named like a product dashboard replaces it in place; any other
# lands in the Custom folder, keeping its subdirectory so two custom files with
# the same name in different subdirectories do not overwrite each other.
if [ -d "/custom/dashboards" ]; then
    find /custom/dashboards -type f -name '*.json' | while read -r f; do
        product=$(find "$PROV/dashboards" -type f -name "$(basename "$f")" | head -1)
        if [ -n "$product" ]; then
            cp "$f" "$product"
        else
            rel=${f#/custom/dashboards/}
            mkdir -p "$PROV/custom_dashboards/$(dirname "$rel")"
            cp "$f" "$PROV/custom_dashboards/$rel"
        fi
    done
fi

# Grafana-managed rules, product or custom, all go in the Alerts folder.
if [ -d "/custom/alerting" ]; then
    cp -RT /custom/alerting/ "$PROV/alerting/"
fi

# Grafana crash-loops on a Telegram contact point with an empty bot token, so
# the alerting files that declare one only ship when Telegram is configured.
# The same conditions are evaluated by vmalert (docker/vmalert/rules).
if [ -z "$GRAFANA_TELEGRAM_TOKEN" ] || [ -z "$GRAFANA_TELEGRAM_CHAT_ID" ]; then
    rm -f "$PROV/alerting/storage_governor.yaml"
    rm -f "$PROV/alerting/waf_realuser_block.yaml"
else
    # ${VAR} interpolation turns an all-digit chat id into a number and the
    # Telegram chatid field only accepts a string.
    for f in "$PROV"/alerting/*.yaml; do
        [ -e "$f" ] && sed -i "s|\${GRAFANA_TELEGRAM_CHAT_ID}|\"${GRAFANA_TELEGRAM_CHAT_ID}\"|g" "$f"
    done
fi

cat << EOF > "$PROV/jwks.json"
{
    "keys": [
    	{"kty":"oct","alg":"HS256","k":"$(echo -n "$API_ISARDVDI_SECRET" | base64 -w 0 | tr -d '=')"}
    ]
}
EOF

if [ -x "/custom/entrypoint.sh" ]; then
    /custom/entrypoint.sh
fi
