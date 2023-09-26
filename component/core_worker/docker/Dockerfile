FROM python:3.11
COPY component/core_worker/docker/requirements.txt .
RUN pip install -r requirements.txt && \
    rm requirements.txt
ENV PYTHONPATH /opt/isardvdi
COPY component/core_worker/docker/uuidgen.py /opt/isardvdi/uuidgen.py
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY component/core_worker/src /opt/isardvdi/isardvdi_core_worker
# Takes url from RQ_REDIS_URL env var
CMD ["/bin/sh", "-c", "rq worker core -n core:isard-core_worker:$(python3 /opt/isardvdi/uuidgen.py) -P /opt/isardvdi/isardvdi_core_worker"]
