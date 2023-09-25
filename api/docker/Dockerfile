FROM alpine:3.18 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache python3 py3-pip curl openssh-client py3-gevent py3-greenlet py3-pillow  ttf-liberation
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev
COPY api/docker/requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt
RUN apk del .build_deps

COPY api/src /api
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf

ENV PYTHONWARNINGS "ignore:Unverified HTTPS request"
CMD ["python3", "-u", "/api/startv3.py"]

ARG SRC_VERSION_ID
RUN echo -n "$SRC_VERSION_ID" > /version
