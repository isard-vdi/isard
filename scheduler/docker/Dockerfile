FROM alpine:3.22.0 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip curl py3-gevent py3-greenlet

RUN pip3 install --break-system-package --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev
COPY scheduler/docker/requirements.txt /requirements.txt
RUN pip3 install --break-system-package --no-cache-dir -r requirements.txt
RUN apk del .build_deps

COPY scheduler/src /src
COPY component/_common/src /src/scheduler/_common
WORKDIR /src

CMD ["python3", "start.py"]
STOPSIGNAL SIGKILL
USER nobody
