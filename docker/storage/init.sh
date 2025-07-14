#!/bin/sh -i

export STORAGE_DOMAIN
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

REDIS_WORKERS=${REDIS_WORKERS:-1}

if [ "${REDIS_WORKERS}" -eq 0 ]
then
    echo "REDIS_WORKERS is set to 0, not starting any workers, sleeping forever"
    sleep infinity
fi

if ${CAPABILITIES_DISK:-true}
then
    # Wait for Redis to be ready before starting workers
    /utils/wait_for_redis

    for priority in high default low; do
        previous_pools=""

        for pool in $(echo ${CAPABILITIES_STORAGE_POOLS:-00000000-0000-0000-0000-000000000000} | tr "," "\n" | sort); do
            queues="$queues storage.$pool.$priority"

            for previous_pool in $previous_pools; do
                queues="$queues storage.$previous_pool:$pool.$priority"
            done

            previous_pools="$previous_pools $pool"
        done
    done

    for worker in $(seq 1 ${REDIS_WORKERS}); do
        rq worker \
            --connection-class="isardvdi_common.redis_retry.RedisRetry" \
            --url "redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}" \
            --path /opt/isardvdi/isardvdi_task \
            --logging_level ${LOG_LEVEL:-INFO} \
            --with-scheduler \
            --name storage:${STORAGE_DOMAIN:-isard-storage}:$(uuidgen) \
            $queues &
    done
fi

sleep infinity