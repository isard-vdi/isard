FROM influxdb:2.1-alpine
COPY docker/influxdb/setup.sh /docker-entrypoint-initdb.d
HEALTHCHECK --interval=15s CMD influx ping
