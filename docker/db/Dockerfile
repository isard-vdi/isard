FROM rethinkdb:2.4.4-bookworm-slim

RUN apt-get update && \
    apt-get install -y \
        python3-pip \
        iproute2 \
        gawk \
        moreutils && \
    apt-get clean autoclean && \
    apt-get autoremove --yes && \
    rm -rf \
        /var/lib/apt \
        /var/lib/dpkg \
        /var/lib/cache \
        /var/lib/log
RUN pip3 install --no-cache-dir --break-system-packages \
    rethinkdb==2.4.10.post1

COPY docker/db/run.sh /run.sh

ENTRYPOINT [ "/bin/sh" ]
CMD [ "/run.sh" ]
