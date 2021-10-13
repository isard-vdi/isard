FROM registry.gitlab.com/isard/isardvdi/toolbox-base:main as production
MAINTAINER isard <info@isard.com>

COPY docker/toolbox/src /src
COPY docker/toolbox/init.sh /init.sh

CMD ["/bin/sh","/init.sh"]
