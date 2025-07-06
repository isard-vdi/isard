FROM alpine:3.22.0

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip

COPY component/core_worker/docker/requirements.txt .
RUN pip install -r requirements.txt --break-system-package && \
    rm requirements.txt
ENV PYTHONPATH /opt/isardvdi
COPY component/core_worker/docker/uuidgen.py /opt/isardvdi/uuidgen.py
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY component/core_worker/src /opt/isardvdi/isardvdi_core_worker
COPY pkg/gen/proto/python_old /opt/isardvdi/isardvdi_protobuf_old
# Takes url from RQ_REDIS_URL env var
CMD ["/bin/sh", "-c", "REDIS_WORKERS=${REDIS_WORKERS:-3}; for i in $(seq 1 $REDIS_WORKERS); do rq worker --connection-class='isardvdi_common.redis_retry.RedisRetry' --worker-class='isardvdi_common.worker.Worker' core.feedback core -n core:isard-core_worker:$(python3 /opt/isardvdi/uuidgen.py) -P /opt/isardvdi/isardvdi_core_worker & done; wait"]
USER nobody