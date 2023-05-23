#!/bin/sh -i

export STORAGE_DOMAIN

export PYTHONWARNINGS="ignore:Unverified HTTPS request"
python3 /api/start.py &
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
  rq worker --url "redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}" -P /opt/isardvdi/isardvdi_task $queues &
fi

# Wait background tasks and clean it at termination.
stop_background_tasks()
{
  echo Stopping background tasks...
  trap - SIGTERM
  kill -TERM -$$
  wait
}
trap stop_background_tasks SIGTERM SIGINT SIGQUIT 
wait
