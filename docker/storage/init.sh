#!/bin/sh -i

export STORAGE_DOMAIN
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

if ${CAPABILITIES_DISK:-true}
then
  for priority in high default low
  do
    previous_pools=""
    for pool in $(echo ${CAPABILITIES_STORAGE_POOLS:-00000000-0000-0000-0000-000000000000} | tr "," "\n" | sort)
    do
      queues="$queues storage.$pool.$priority"
      for previous_pool in $previous_pools
      do
        queues="$queues storage.$previous_pool:$pool.$priority"
      done
      previous_pools="$previous_pools $pool"
    done
  done
  for worker in $(seq 1 ${REDIS_WORKERS:-1})
  do
    rq worker --connection-class="isardvdi_common.redis_retry.RedisRetry" --name storage:${STORAGE_DOMAIN:-isard-storage}:$(uuidgen) --url "redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}" -P /opt/isardvdi/isardvdi_task $queues
  done
fi
