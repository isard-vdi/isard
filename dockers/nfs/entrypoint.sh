#!/bin/sh -eu
mkdir -p /nfs/images
/usr/sbin/exportfs -r
/sbin/rpcbind --
/usr/sbin/rpc.nfsd |:
/usr/sbin/rpc.mountd -F

