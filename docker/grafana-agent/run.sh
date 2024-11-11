#!/bin/bash

set -xe

apt-get update && apt-get install -y wget
wget https://github.com/mikefarah/yq/releases/download/v4.27.5/yq_linux_amd64 -O /usr/bin/yq
chmod +x /usr/bin/yq

if [[ ("$FLAVOUR" == "all-in-one" || "$FLAVOUR" == "web" || -z "$FLAVOUR") && "$ENABLE_STATS" != "false" ]]; then
    yq '. *+ load("/etc/agent/web.yml")' /etc/agent/config.yml > /etc/agent/agent.yml

elif [[ ("$FLAVOUR" == "hypervisor" || "$FLAVOUR" == "video-standalone") && "$ENABLE_STATS" != "false" ]]; then
    yq '. *+ load("/etc/agent/video.yml")' /etc/agent/config.yml > /etc/agent/agent.yml

elif [[ "$FLAVOUR" == "monitor" && "$ENABLE_STATS" != "false" ]]; then
    yq '. *+ load("/etc/agent/monitor.yml")' /etc/agent/config.yml > /etc/agent/agent.yml

else
    cp /etc/agent/config.yml /etc/agent/agent.yml
fi

find /custom -name "*.yml" | xargs -I% yq -i '. *+ load("%")' /etc/agent/agent.yml

/bin/grafana-agent -config.file=/etc/agent/agent.yml -config.expand-env=true --metrics.wal-directory=/tmp/agent/data
