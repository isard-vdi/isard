FROM alpine:3.22

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip

COPY component/core_worker/docker/requirements.txt .
RUN pip install -r requirements.txt --break-system-package && \
    rm requirements.txt
ENV PYTHONPATH /opt/isardvdi
COPY component/core_worker/docker/uuidgen.py /opt/isardvdi/uuidgen.py
COPY component/_common/isardvdi_common /opt/isardvdi/isardvdi_common
COPY component/core_worker/src /opt/isardvdi/isardvdi_core_worker
COPY pkg/gen/proto/python_old /opt/isardvdi/isardvdi_protobuf_old
CMD ["/bin/sh", "-c", "REDIS_WORKERS=${REDIS_WORKERS:-3}; for i in $(seq 1 $REDIS_WORKERS); do rq worker --url \"redis://:${REDIS_PASSWORD}@${REDIS_HOST:-isard-redis}:${REDIS_PORT:-6379}/0\" --connection-class='isardvdi_common.connections.redis_retry.RedisRetry' --worker-class='isardvdi_common.helpers.worker.Worker' core.feedback core -n core:isard-core_worker:$(python3 /opt/isardvdi/uuidgen.py) -P /opt/isardvdi/isardvdi_core_worker --with-scheduler & done; wait"]
USER nobody
