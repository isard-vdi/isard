FROM python:3.9
RUN pip install "rq~=1.14" "rethinkdb~=2.4" "requests~=2.30" "python-jose~=3.3" "cachetools~=5.3"
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY component/core_worker/src /opt/isardvdi/isardvdi_core_worker
# Takes url from RQ_REDIS_URL env var
CMD ["rq", "worker", "core", "-n", "api:isard-core_worker", "-P", "/opt/isardvdi/isardvdi_core_worker"]
