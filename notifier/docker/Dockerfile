FROM alpine:3.19

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip uuidgen

COPY notifier/docker/requirements.txt .
RUN pip install -r requirements.txt --break-system-package && \
    rm requirements.txt
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY notifier/src /opt/isardvdi/src
WORKDIR /opt/isardvdi/src

# Takes url from RQ_REDIS_URL env var
CMD ["/bin/sh", "-c", "rq worker notifier.default -n notifier:isard-notifier:$(uuidgen) -P /opt/isardvdi/src/notifier/lib & python3 -u /opt/isardvdi/src/start.py"]
USER nobody