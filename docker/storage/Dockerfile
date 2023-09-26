FROM registry.gitlab.com/isard/isardvdi/storage-base:main as production
MAINTAINER isard <info@isard.com>

COPY docker/storage/requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

ENV PYTHONPATH /opt/isardvdi
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY docker/storage/task /opt/isardvdi/isardvdi_task
COPY docker/storage/init.sh /init.sh

CMD ["/init.sh"]

