#!/bin/bash
set -e

influx bucket create \
    -o ${DOCKER_INFLUXDB_INIT_ORG} \
    -n ${DOCKER_INFLUXDB_INIT_BUCKET}-go

influx bucket create \
    -o ${DOCKER_INFLUXDB_INIT_ORG} \
    -n glances \
    -r ${STATS_GLANCES_DATA_RETENTION}

GLANCES_BUCKET_ID=$(influx bucket list -n glances --hide-headers | awk '{ print $1 }')

influx v1 dbrp create \
    -o ${DOCKER_INFLUXDB_INIT_ORG} \
    --bucket-id ${GLANCES_BUCKET_ID} \
    --db glances \
    --rp glances \
    --default

influx v1 auth create \
    -o ${DOCKER_INFLUXDB_INIT_ORG} \
    --username admin \
    --password ${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN} \
    --read-bucket ${GLANCES_BUCKET_ID} \
    --write-bucket ${GLANCES_BUCKET_ID}
