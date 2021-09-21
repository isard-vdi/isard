#!/bin/bash

bucket_id=$(influx bucket list -n isardvdi |grep isardvdi | cut -f1)
influx auth create --write-bucket $bucket_id -o isardvdi -d hypervisor_remote_bucket_token -u admin -t $INFLUXDB_ADMIN_TOKEN_SECRET

influx bucket create -o isardvdi -n isardvdi-go
bucket_id=$(influx bucket list -n isardvdi-go |grep isardvdi | cut -f1)
influx auth create --write-bucket $bucket_id -o isardvdi -d hypervisor_remote_bucket_token -u admin -t $INFLUXDB_ADMIN_TOKEN_SECRET

