#!/bin/sh -i

export STORAGE_DOMAIN

export PYTHONWARNINGS="ignore:Unverified HTTPS request"
python3 /api/start.py &
if ${CAPABILITIES_DISK:-true}
then
  for priority in high default low
  do
    for pool in $(echo ${CAPABILITIES_STORAGE_POOLS:-00000000-0000-0000-0000-000000000000} | tr "," " ")
    do
      queues="$queues storage.$pool.$priority"
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
