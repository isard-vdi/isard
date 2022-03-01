#!/bin/bash

if [ -z "$INFLUXDB_ADDRESS" ]; then
    if [ -z "$DOCKER_NET" ]; then
        export DOCKER_NET="172.31.255"
    fi

    export INFLUXDB_PROTOCOL="http"
    export INFLUXDB_HOST="$DOCKER_NET.12"
    export INFLUXDB_PORT="8086"
else
    export INFLUXDB_PROTOCOL="$(echo "$INFLUXDB_ADDRESS" | sed -n 's/^\([a-z]*\):.*$/\1/p')"

    influxdb_hostport="$(echo $INFLUXDB_ADDRESS | echo ${INFLUXDB_ADDRESS/$INFLUXDB_PROTOCOL/} | cut -c4-)"
    export INFLUXDB_PORT="$(echo $influxdb_hostport | sed -n 's/^.*:\([0-9]*\)$/\1/p')"

    if [ "$INFLUXDB_PORT" == "" ]; then
        export INFLUXDB_HOST=$influxdb_hostport

        if [ $INFLUXDB_PROTOCOL == "https" ]; then
            export INFLUXDB_PORT="443"
        else
            export INFLUXDB_PORT="80"
        fi
    else
        export INFLUXDB_HOST="$(echo ${influxdb_hostport/$INFLUXDB_PORT/} | sed 's/.$//')"
    fi
fi

if [ -z "$STATS_GLANCES_REFRESH" ]; then
    export STATS_GLANCES_REFRESH=2
fi

export STATS_GLANCES_HISTORY_SIZE=$(printf %.0f "$((3600 / $STATS_GLANCES_REFRESH))")

eval "echo \"$(cat /glances/conf/glances.conf.template)\" > /glances/conf/glances.conf"

python -m glances -C /glances/conf/glances.conf --export influxdb -q --disable-process
