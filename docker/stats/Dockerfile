FROM alpine:3.11.3 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    gcc \
    linux-headers
RUN apk add --no-cache python3 docker py3-libvirt
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir psutil requests docker xmltodict ipython redis rethinkdb==2.3.0.post6
RUN apk del .build_deps

RUN apk add util-linux

ADD docker/stats/src /src
WORKDIR /src
CMD ["python3", "run.py"]

FROM production as development
CMD ["/sleep","10000"]
