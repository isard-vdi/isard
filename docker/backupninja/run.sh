#!/bin/sh

if [ "$BACKUP_NFS_ENABLED" = "true" ]
then
    echo "TESTING THAT NFS FOLDER CAN BE MOUNTED AND UNMOUNTED..."
    mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
    if grep -qs '/backup ' /proc/mounts; then
        echo "  - OK: BACKUP NFS FOLDER MOUNTED: $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup"
    else
        echo "  - ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup!!!. Exitting!"
        exit 1
    fi
fi
mkdir -p /backup/db
borg init -e none /backup/db > /dev/null 2>&1
mkdir -p /backup/disks
borg init -e none /backup/disks > /dev/null 2>&1
mkdir -p /backup/extract

# Unmount if nfs as it will be mounted at backup cron time
if [ "$BACKUP_NFS_ENABLED" = "true" ]
then
    umount -f -l /backup
    if grep -qs '/backup ' /proc/mounts; then
        df -h
        echo -e "  - ERROR!!! UNABLE TO UnMOUNT /backup. Exitting!\n"
        exit 1
    else
        echo -e "  - OK: BACKUP NFS UnMOUNTED\n"
    fi
fi

LOG_FILE="/var/log/backupninja.log"
touch $LOG_FILE

sed -i '/^logfile =/d' /usr/local/etc/backupninja.conf
echo "logfile = $LOG_FILE" >> /usr/local/etc/backupninja.conf

rm -f /usr/local/etc/backup.d/*

# BACKUP NFS MOUNT / UMOUNT
if [ "$BACKUP_NFS_ENABLED" = "true" ]
then
    echo "SETTING NFS MOUNT: mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup"
    echo "                   Logs can be found at $LOG_FILE folder"

    cat <<EOT >> /usr/local/etc/backup.d/15.nfs-db-mount.sh
when = $BACKUP_DB_WHEN

mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "BACKUP NFS FOLDER MOUNTED: $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
else
    echo "ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER !!!"
    exit 1
fi
EOT

    cat <<EOT >> /usr/local/etc/backup.d/35.nfs-db-unmount.sh
when = $BACKUP_DB_WHEN

umount -f -l /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "ERROR!!! UNABLE TO UNMOUNT /backup"
    exit 1
else
    echo "BACKUP NFS UnMOUNTED"
fi
EOT

    cat <<EOT >> /usr/local/etc/backup.d/36.nfs-disks-mount.sh
when = $BACKUP_DISKS_WHEN

mount -t nfs4 $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "BACKUP NFS FOLDER MOUNTED: $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER"
else
    echo "ERROR!!! UNABLE TO MOUNT $BACKUP_NFS_SERVER:$BACKUP_NFS_FOLDER !!!"
    exit 1
fi
EOT

    cat <<EOT >> /usr/local/etc/backup.d/95.nfs-disks-unmount.sh
when = $BACKUP_DISKS_WHEN

umount -f -l /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "ERROR!!! UNABLE TO UNMOUNT /backup"
    exit 1
else
    echo "BACKUP NFS UnMOUNTED"
fi
EOT
fi

# BACKUP DB SCRIPT
if [ "$BACKUP_DB_ENABLED" = "true" ]
then
    echo "DATABASE ENABLED: Enabled database backup $BACKUP_DB_WHEN with $BACKUP_DB_PRUNE prune policy"
    echo "                  Logs can be found at $LOG_FILE folder"

    cat <<EOT >> /usr/local/etc/backup.d/10.info.sh
when = $BACKUP_DB_WHEN

EOT

    cat <<'EOT' >> /usr/local/etc/backup.d/10.info.sh
echo "----------- NEW DATABASE BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $LOG_FILE
EOT

    cat <<EOT >> /usr/local/etc/backup.d/20.dbdump.sh
when = $BACKUP_DB_WHEN

rm -f /dbdump/isard-db*.tar.gz
EOT
    cat <<'EOT' >> /usr/local/etc/backup.d/20.dbdump.sh
/usr/bin/rethinkdb-dump -c "isard-db:28015" -f "/dbdump/isard-db-$(date +%Y-%m-%d_%H:%M:%S).tar.gz"
EOT

    cat <<EOT >> /usr/local/etc/backup.d/30.dbborg.borg
when = $BACKUP_DB_WHEN

[source]
include = /dbdump

## for more info see : borg prune -h
keep = 0
prune = yes
prune_options = $BACKUP_DB_PRUNE

[dest]
directory = /backup/db
host = localhost
port = 22
user = root
archive = {now:%Y-%m-%dT%H:%M:%S}
compression = lz4
encryption = none
passphrase = 
EOT
fi

## BACKUP DISKS SCRIPT
if [ "$BACKUP_DISKS_TEMPLATES_ENABLED" = "false" ]; then
    BACKUP_DISKS_TEMPLATES_ENABLED=""
else
    BACKUP_DISKS_TEMPLATES_ENABLED="include = /opt/isard/templates"
fi
if [ "$BACKUP_DISKS_GROUPS_ENABLED" = "false" ]; then
    BACKUP_DISKS_GROUPS_ENABLED=""
else
    BACKUP_DISKS_GROUPS_ENABLED="include = /opt/isard/groups"
fi
if [ "$BACKUP_DISKS_MEDIA_ENABLED" = "false" ]; then
    BACKUP_DISKS_MEDIA_ENABLED=""
else
    BACKUP_DISKS_MEDIA_ENABLED="include = /opt/isard/media"
fi

if [ "$BACKUP_DISKS_ENABLED" = "true" ]
then
    echo "DISKS ENABLED: Enabled disks backup $BACKUP_DISKS_WHEN with $BACKUP_DISKS_PRUNE prune policy"
    echo "               Disks backup included folders:"
    echo "               - TEMPLATES: $BACKUP_DISKS_TEMPLATES_ENABLED"
    echo "               -    GROUPS: $BACKUP_DISKS_GROUPS_ENABLED"
    echo "               -     MEDIA: $BACKUP_DISKS_MEDIA_ENABLED"
    echo "               Logs can be found at $LOG_FILE folder"

    cat <<EOT >> /usr/local/etc/backup.d/40.info.sh
when = $BACKUP_DISKS_WHEN

EOT
    cat <<'EOT' >> /usr/local/etc/backup.d/40.info.sh
echo "----------- NEW DISKS BACKUP: $(date +%Y-%m-%d_%H:%M:%S) -----------" >> $LOG_FILE
EOT

    cat <<EOT >> /usr/local/etc/backup.d/50.disksborg.borg
when = $BACKUP_DISKS_WHEN

[source]
$BACKUP_DISKS_TEMPLATES_ENABLED
$BACKUP_DISKS_GROUPS_ENABLED
$BACKUP_DISKS_MEDIA_ENABLED

## for more info see : borg prune -h
keep = 0
prune = yes
prune_options = $BACKUP_DISKS_PRUNE

[dest]
directory = /backup/disks
host = localhost
port = 22
user = root
archive = {now:%Y-%m-%dT%H:%M:%S}
compression = lz4
encryption = none
passphrase = 
EOT
fi

chmod 600 /usr/local/etc/backup.d/* > /dev/null 2>&1
crond
tail -f $LOG_FILE
