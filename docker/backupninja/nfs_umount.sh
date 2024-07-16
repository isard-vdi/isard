#!/bin/sh

umount -f -l /backup
if grep -qs '/backup ' /proc/mounts; then
    echo "ERROR!!! UNABLE TO UNMOUNT /backup"
    exit 1
else
    echo "BACKUP NFS UnMOUNTED"
fi