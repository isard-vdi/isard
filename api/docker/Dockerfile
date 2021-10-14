FROM alpine:3.12.0 as production
MAINTAINER isard <info@isard.com>

RUN apk add --no-cache python3 py3-pip py3-pyldap~=3.2.0
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev 
COPY api/docker/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

RUN apk add --no-cache curl openssh-client

COPY api/src /api
COPY api/docker/run.sh /
#EXPOSE 7039
# WORKDIR /api
# CMD [ "python3", "start.py" ]

CMD /run.sh

ARG SRC_VERSION_ID
RUN echo -n "$SRC_VERSION_ID" > /version
