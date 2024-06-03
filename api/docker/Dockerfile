FROM alpine:3.19 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache
RUN apk add --no-cache python3 py3-pip curl openssh-client py3-gevent py3-greenlet ttf-liberation

RUN pip3 install --break-system-package --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev
COPY api/docker/requirements.txt /requirements.txt
RUN pip3 install --break-system-package --no-cache-dir -r requirements.txt
RUN apk del .build_deps

COPY api/src /api
ENV PYTHONPATH /opt/isardvdi:/opt/isardvdi/isardvdi_protobuf
COPY component/_common/src /opt/isardvdi/isardvdi_common
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf
COPY pkg/gen/proto/python_old /opt/isardvdi/isardvdi_protobuf_old

ENV PYTHONWARNINGS "ignore:Unverified HTTPS request"
CMD ["python3", "-u", "/api/startv3.py"]

ARG SRC_VERSION_ID
RUN echo -n "$SRC_VERSION_ID" > /version
