FROM registry.gitlab.com/isard/isardvdi/storage-base:main as production
MAINTAINER isard <info@isard.com>

COPY docker/storage/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3

COPY docker/storage/api /api
COPY component/_common/src /api/api/_common
COPY docker/storage/init.sh /init.sh

CMD ["/init.sh"]

