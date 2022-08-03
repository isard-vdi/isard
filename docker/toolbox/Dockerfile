FROM registry.gitlab.com/isard/isardvdi/toolbox-base:main as production
MAINTAINER isard <info@isard.com>

COPY docker/toolbox/src /src
COPY docker/toolbox/api /api
COPY docker/toolbox/init.sh /init.sh
COPY docker/toolbox/requirements.pip3 /requirements.pip3

RUN pip3 install --no-cache-dir -r requirements.pip3
CMD ["/bin/sh","/init.sh"]

