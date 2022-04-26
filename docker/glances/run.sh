#!/bin/bash

if [ -z "$STATS_GLANCES_REFRESH" ]; then
    export STATS_GLANCES_REFRESH=2
fi

export STATS_GLANCES_HISTORY_SIZE=$(printf %.0f "$((3600 / $STATS_GLANCES_REFRESH))")

eval "echo \"$(cat /glances/conf/glances.conf.template)\" > /glances/conf/glances.conf"

python -m glances -C /glances/conf/glances.conf --export prometheus -q --disable-process
