FROM alpine:3.12.0 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache python3 py3-pip py3-gevent py3-greenlet curl
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev
COPY scheduler/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

COPY scheduler/src /src
WORKDIR /src

CMD ["python3","-u","start.py"]
HEALTHCHECK --interval=10s CMD curl -f http://localhost:5000/scheduler/healthcheck
STOPSIGNAL SIGKILL
