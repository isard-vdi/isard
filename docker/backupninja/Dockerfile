FROM alpine:3.15.0 as build
MAINTAINER isard <info@isard.com>
RUN apk add --no-cache \
    automake \
    autoconf \
    bash \
    gcc \
    git \
    make
RUN git clone https://0xacab.org/liberate/backupninja.git && \
    cd backupninja && \
    bash ./autogen.sh && bash configure && \
    make && make install

FROM alpine:3.14.0 as production
MAINTAINER isard <info@isard.com>
RUN apk add --no-cache nfs-utils
COPY --from=build /usr/local/sbin/backupninja /usr/local/sbin/backupninja
COPY --from=build /usr/local/sbin/ninjahelper /usr/local/sbin/ninjahelper
COPY --from=build /usr/local/etc/backupninja.conf /usr/local/etc/backupninja.conf
COPY --from=build /usr/local/lib/backupninja /usr/local/lib/backupninja
COPY --from=build /usr/local/share/backupninja /usr/local/share/backupninja
RUN sed -i '/^reportemail =/s/^/#/' /usr/local/etc/backupninja.conf
RUN ln -s /usr/local/sbin/backupninja /etc/periodic/hourly/backupninja
RUN mkdir -p -m700 /usr/local/etc/backup.d
RUN mkdir -p /usr/local/var/log
RUN mkdir /backup
RUN mkdir /dbdump
WORKDIR /
COPY docker/backupninja/run.sh /usr/local/bin/
COPY docker/backupninja/backup.sh /usr/local/bin/
RUN apk add --no-cache \
    bash \
    borgbackup \
    coreutils \
    flock \
    py3-pip
## Optional packages
#cryptsetup duplicity flashrom gzip hwinfo rdiff-backup restic rsync sfdisk
RUN pip3 install --no-cache-dir \
    rethinkdb
CMD [ "run.sh" ]