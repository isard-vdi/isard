FROM alpine:3.20 as build
MAINTAINER isard <info@isard.com>
RUN apk add --no-cache \
    automake \
    autoconf \
    bash \
    gcc \
    git \
    make
RUN git clone https://gitlab.com/isard/backupninja.git && \
    cd backupninja && \
    bash ./autogen.sh && bash configure && \
    make && make install

FROM alpine:3.20 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache

RUN apk add --no-cache \
    bash \
    envsubst \
    nfs-utils \
    borgbackup \
    redis \
    coreutils \
    flock \
    py3-pip
## Optional packages
#cryptsetup duplicity flashrom gzip hwinfo rdiff-backup restic rsync sfdisk

RUN pip3 install \
    --no-cache-dir \
    --break-system-packages \
    rethinkdb

# Install backupninja
COPY --from=build /usr/local/sbin/backupninja /usr/local/sbin/backupninja
COPY --from=build /usr/local/sbin/ninjahelper /usr/local/sbin/ninjahelper
COPY --from=build /usr/local/etc/backupninja.conf /usr/local/etc/backupninja.conf
COPY --from=build /usr/local/lib/backupninja /usr/local/lib/backupninja
COPY --from=build /usr/local/share/backupninja /usr/local/share/backupninja
RUN sed -i '/^reportemail =/s/^/#/' /usr/local/etc/backupninja.conf
RUN ln -s /usr/local/sbin/backupninja /etc/periodic/hourly/backupninja

# Copy scripts
COPY docker/backupninja/run.sh /usr/local/bin/
COPY docker/backupninja/backup.sh /usr/local/bin/
COPY docker/backupninja/nfs_mount.sh /usr/local/bin/
COPY docker/backupninja/nfs_umount.sh /usr/local/bin/
COPY docker/backupninja/backup.d /usr/local/share/backup.d

WORKDIR /

ENTRYPOINT [ "run.sh" ]
