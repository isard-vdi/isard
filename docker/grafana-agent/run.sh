#!/bin/bash

set -xe

if [[ ("$FLAVOUR" == "all-in-one" || "$FLAVOUR" == "web" || -z "$FLAVOUR") && "$ENABLE_STATS" != "false" ]]; then
    apt-get update && apt-get install -y wget
    wget https://github.com/mikefarah/yq/releases/download/v4.27.5/yq_linux_amd64 -O /usr/bin/yq
    chmod +x /usr/bin/yq
    yq '. *+ load("/etc/agent/db.yml")' /etc/agent/config.yml > /etc/agent/agent.yml
else
    cp /etc/agent/config.yml /etc/agent/agent.yml
fi

/bin/agent -config.file=/etc/agent/agent.yml -config.expand-env=true --metrics.wal-directory=/tmp/agent/data
