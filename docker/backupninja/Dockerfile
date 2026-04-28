FROM alpine:3.22 AS backupninja-src
RUN apk add --no-cache automake autoconf bash gcc git make
RUN git clone https://gitlab.com/isard/backupninja.git && \
    cd backupninja && \
    bash ./autogen.sh && bash configure && \
    make && make install

FROM python:3.13-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

RUN apk add --no-cache build-base libffi-dev libjpeg-turbo-dev musl-dev openssl-dev zlib-dev

WORKDIR /workspace
COPY . .
RUN uv sync --frozen --no-dev --package isardvdi-backupninja --no-editable

FROM alpine:3.22 AS runtime
RUN apk -U upgrade --no-cache
RUN apk add --no-cache \
    bash borgbackup coreutils curl envsubst flock jq libffi libjpeg-turbo \
    nfs-utils openssl redis zlib

COPY --from=builder /workspace/.venv /.venv
ENV PATH="/.venv/bin:$PATH"

COPY --from=backupninja-src /usr/local/sbin/backupninja /usr/local/sbin/backupninja
COPY --from=backupninja-src /usr/local/sbin/ninjahelper /usr/local/sbin/ninjahelper
COPY --from=backupninja-src /usr/local/etc/backupninja.conf /usr/local/etc/backupninja.conf
COPY --from=backupninja-src /usr/local/lib/backupninja /usr/local/lib/backupninja
COPY --from=backupninja-src /usr/local/share/backupninja /usr/local/share/backupninja
RUN sed -i '/^reportemail =/s/^/#/' /usr/local/etc/backupninja.conf
RUN sed -i '/^reportprom =/s/^/#/' /usr/local/etc/backupninja.conf
RUN sed -i 's|^configdirectory = /etc/backup.d|configdirectory = /usr/local/etc/backup.d|' /usr/local/etc/backupninja.conf
RUN ln -s /usr/local/sbin/backupninja /etc/periodic/hourly/backupninja

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
