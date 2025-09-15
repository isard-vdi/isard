FROM alpine:3.22.0 as build
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

FROM alpine:3.22.0 as production
MAINTAINER isard <info@isard.com>

RUN apk -U upgrade --no-cache

RUN apk add --no-cache \
    bash \
    envsubst \
    nfs-utils \
    borgbackup \
    redis \
    curl \
    coreutils \
    flock \
    py3-pip \
    jq
## Optional packages
#cryptsetup duplicity flashrom gzip hwinfo rdiff-backup restic rsync sfdisk

RUN pip3 install \
    --no-cache-dir \
    --break-system-packages \
    rethinkdb \
    requests \
    pyjwt

# Set up Python path for common imports
ENV PYTHONPATH /opt/isardvdi
COPY component/_common/src /opt/isardvdi/isardvdi_common

# Install backupninja
COPY --from=build /usr/local/sbin/backupninja /usr/local/sbin/backupninja
COPY --from=build /usr/local/sbin/ninjahelper /usr/local/sbin/ninjahelper
COPY --from=build /usr/local/etc/backupninja.conf /usr/local/etc/backupninja.conf
COPY --from=build /usr/local/lib/backupninja /usr/local/lib/backupninja
COPY --from=build /usr/local/share/backupninja /usr/local/share/backupninja
RUN sed -i '/^reportemail =/s/^/#/' /usr/local/etc/backupninja.conf
RUN sed -i '/^reportprom =/s/^/#/' /usr/local/etc/backupninja.conf
RUN ln -s /usr/local/sbin/backupninja /etc/periodic/hourly/backupninja

# Copy scripts
COPY docker/backupninja/run.sh /usr/local/bin/
COPY docker/backupninja/nfs_mount.sh /usr/local/bin/
COPY docker/backupninja/nfs_umount.sh /usr/local/bin/
COPY docker/backupninja/backup_report.py /usr/local/bin/
COPY docker/backupninja/send_backup_report.sh /usr/local/bin/
COPY docker/backupninja/borg_integrity_template.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup_report.py
RUN chmod +x /usr/local/bin/send_backup_report.sh
RUN chmod +x /usr/local/bin/borg_integrity_template.sh
COPY docker/backupninja/backup.d /usr/local/share/backup.d

WORKDIR /

ENTRYPOINT [ "run.sh" ]
