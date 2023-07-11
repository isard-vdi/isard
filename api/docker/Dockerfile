FROM alpine:3.18 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache python3 py3-pip curl openssh-client py3-gevent py3-greenlet py3-pillow  ttf-liberation
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev
COPY api/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

COPY api/src /api
COPY component/_common/src /api/api/_common
ENV PYTHONPATH /opt/isardvdi
COPY pkg/gen/proto/python /opt/isardvdi/isardvdi_protobuf

ENV PYTHONWARNINGS "ignore:Unverified HTTPS request"
CMD ["python3", "-u", "/api/startv3.py"]
HEALTHCHECK --interval=10s CMD curl -f http://localhost:5000/api/v3

ARG SRC_VERSION_ID
RUN echo -n "$SRC_VERSION_ID" > /version
