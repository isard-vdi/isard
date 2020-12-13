FROM alpine:3.12.0 as production
MAINTAINER isard <info@isardvdi.com>

RUN apk add --no-cache --update wireguard-tools openssh python3
RUN rm -rf /etc/ssh/ssh_host_rsa_key /etc/ssh/ssh_host_dsa_key

## From isard-api
RUN apk add python3 py3-pip
RUN pip3 install --upgrade pip
RUN apk add --no-cache --virtual .build_deps \
    build-base \
    python3-dev \
    libffi-dev \
    openssl-dev \ 
    autoconf \
    automake \
    libtool \
    libmnl-dev \
    libnftnl-dev \
    git

# python-iptables
RUN git clone git://git.netfilter.org/iptables && cd iptables && \
    ./autogen.sh && \
    ./configure --prefix=/tmp/iptables && \
    make && make install && cd .. && rm -rf iptables

ENV IPTABLES_LIBDIR=/tmp/iptables/lib
ENV XTABLES_LIBDIR=/tmp/iptables/lib/xtables

# python requirements
COPY docker/vpn/requirements.pip3 /requirements.pip3
RUN pip3 install --no-cache-dir -r requirements.pip3
RUN apk del .build_deps

COPY docker/vpn/src /src
COPY docker/vpn/run.sh /
COPY docker/vpn/networking.py /

CMD [ "sh", "run.sh"]

