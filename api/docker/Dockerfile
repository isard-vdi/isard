FROM alpine:3.12.0 as production
MAINTAINER isard <info@isard.com>

RUN apk add python3 py3-pip
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev 
COPY api/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

RUN apk add curl

COPY api/src /api

#EXPOSE 7039
WORKDIR /api
CMD [ "python3", "start.py" ]

