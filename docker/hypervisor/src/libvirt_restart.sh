#!/bin/sh -i

echo "Killing virtlogd and libvirtd..."
pkill virtlogd
sleep 1
pkill libvirtd
sleep 1

echo "Starting virtlogd and libvirtd..."
/usr/sbin/virtlogd -d
sleep 4
/usr/sbin/libvirtd -d

false
while [ $? -ne 0 ]; do
  sleep 1
  echo "Waiting for libvirt to start..."
  virsh list >/dev/null 2>&1
done
echo "Libvirt started!"