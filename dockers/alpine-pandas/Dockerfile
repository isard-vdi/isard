FROM alpine:latest
MAINTAINER isard <info@isard.com>

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories
RUN apk update
RUN apk add --no-cache python3 && \
    python3 -m ensurepip && \
    rm -r /usr/lib/python*/ensurepip && \
    pip3 install --upgrade pip setuptools && \
    if [ ! -e /usr/bin/pip ]; then ln -s pip3 /usr/bin/pip ; fi && \
    if [[ ! -e /usr/bin/python ]]; then ln -sf /usr/bin/python3 /usr/bin/python; fi && \
    rm -r /root/.cache
RUN ln -s /usr/include/locale.h /usr/include/xlocale.h
RUN apk add --no-cache --virtual .build_deps build-base python3-dev libffi-dev openssl-dev 
RUN pip3 install pandas
RUN apk del .build_deps
CMD ["python3"]
